"""
GP Evolution Engine — DEAP-powered strategy discovery (pair mode).

Evolves populations of **entry/exit tree pairs** using:
  - Tournament selection with diversity pressure
  - Subtree crossover + mutation on both trees independently
  - Bloat control (max tree depth) on each tree
  - Custom hall of fame for pair individuals
  - Walk-forward validation on top performers

Each individual is a list ``[EntryTree, ExitTree]`` where both trees
are standard DEAP ``PrimitiveTree`` objects sharing the same pset.
The entry tree defines *when to buy*, the exit tree defines *when to sell*.
"""

from __future__ import annotations

import random
from functools import partial
from typing import Any

import numpy as np
import pandas as pd
from deap import base, creator, tools, gp  # type: ignore[import-untyped]

from src.agent.grammar import create_pset, set_context
from src.agent.fitness import evaluate_tree, decode_strategy  # backward compat
from src.agent.fitness import evaluate_pair, decode_pair


# ---------------------------------------------------------------------------
# Pair Hall-of-Fame
# ---------------------------------------------------------------------------

class PairHallOfFame:
    """Simple hall of fame for pair individuals (list of two trees).

    DEAP's built-in ``HallOfFame`` relies on ``==`` comparison which does
    not behave predictably on list-based individuals.  This implementation
    keeps the top *maxsize* unique individuals sorted by fitness (descending).
    """

    def __init__(self, maxsize: int) -> None:
        self.maxsize = maxsize
        self.items: list = []

    def update(self, population: list) -> None:
        for ind in population:
            if not ind.fitness.valid:
                continue
            self.items.append(ind)
        # Sort descending by fitness
        self.items.sort(key=lambda x: x.fitness.values[0], reverse=True)
        # Deduplicate by expression pair
        seen: set[tuple[str, str]] = set()
        unique: list = []
        for ind in self.items:
            key = (str(ind[0]), str(ind[1]))
            if key not in seen:
                seen.add(key)
                unique.append(ind)
        self.items = unique[: self.maxsize]

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx):
        return self.items[idx]

    def __iter__(self):
        return iter(self.items)


# ---------------------------------------------------------------------------
# Strategy signature (diversity helper)
# ---------------------------------------------------------------------------

def _get_strategy_signature(individual) -> frozenset[str]:
    """Extract a rough 'family' signature from a pair of GP trees.

    Looks at the set of primitive (function/terminal) names used across
    *both* the entry and exit trees and returns a frozenset.  Two
    individuals with the same signature are considered to belong to
    the same family.
    """
    names: set[str] = set()
    for tree in individual:  # iterate over entry and exit trees
        for node in tree:
            if isinstance(node, gp.Primitive):
                names.add(node.name)
            elif isinstance(node, gp.Terminal):
                # Skip ephemeral constants (ARG0, random floats, etc.)
                if not node.name.startswith("ARG") and not node.name.startswith("ERCrand"):
                    names.add(node.name)
    return frozenset(names)


# ---------------------------------------------------------------------------
# Tournament selection with diversity pressure
# ---------------------------------------------------------------------------

def selTournamentDiversity(
    individuals: list,
    k: int,
    tournsize: int = 5,
    max_per_family: int = 3,
) -> list:
    """Tournament selection with diversity pressure (niching).

    Runs standard tournament selection but caps the number of selected
    individuals from the same family (signature) to *max_per_family*.
    When the cap is hit, duplicates are replaced with random individuals
    from under-represented families.

    Interface matches DEAP selectors: ``(individuals, k, **kw) -> list``.
    """
    # --- Phase 1: standard tournament selection ---
    selected: list = []
    for _ in range(k):
        aspirants = [random.choice(individuals) for _ in range(tournsize)]
        best = max(aspirants, key=lambda ind: ind.fitness.values[0])
        selected.append(best)

    # --- Phase 2: enforce family caps ---
    family_counts: dict[frozenset[str], int] = {}
    family_members: dict[frozenset[str], list] = {}

    # Index the full population by family for replacement candidates
    for ind in individuals:
        sig = _get_strategy_signature(ind)
        family_members.setdefault(sig, []).append(ind)

    final: list = []
    for ind in selected:
        sig = _get_strategy_signature(ind)
        count = family_counts.get(sig, 0)
        if count < max_per_family:
            final.append(ind)
            family_counts[sig] = count + 1
        else:
            # Pick a replacement from an under-represented family
            under_rep = [
                fam for fam, members in family_members.items()
                if family_counts.get(fam, 0) < max_per_family and members
            ]
            if under_rep:
                replacement_family = random.choice(under_rep)
                replacement = random.choice(family_members[replacement_family])
                final.append(replacement)
                family_counts[replacement_family] = (
                    family_counts.get(replacement_family, 0) + 1
                )
            else:
                # All families are at the cap -- fall back to accepting
                final.append(ind)
                family_counts[sig] = count + 1

    return final


# ---------------------------------------------------------------------------
# Genetic operators for pairs
# ---------------------------------------------------------------------------

def _mate_pair(ind1, ind2, max_depth: int = 8):
    """Crossover: swap entry trees with entry trees, exit with exit.

    Both sub-crossovers use ``gp.cxOnePoint``.  If either resulting tree
    exceeds *max_depth*, that sub-crossover is reverted.
    """
    # Save originals (shallow copy of node lists)
    e1_orig, e2_orig = ind1[0][:], ind2[0][:]
    x1_orig, x2_orig = ind1[1][:], ind2[1][:]

    # Crossover entry trees
    gp.cxOnePoint(ind1[0], ind2[0])
    # Crossover exit trees
    gp.cxOnePoint(ind1[1], ind2[1])

    # Revert entry trees if too deep
    if ind1[0].height > max_depth or ind2[0].height > max_depth:
        ind1[0][:] = e1_orig
        ind2[0][:] = e2_orig
    # Revert exit trees if too deep
    if ind1[1].height > max_depth or ind2[1].height > max_depth:
        ind1[1][:] = x1_orig
        ind2[1][:] = x2_orig

    return ind1, ind2


def _mutate_pair(individual, expr, pset, max_depth: int = 8):
    """Mutate: randomly pick either the entry or exit tree and mutate it.

    Uses ``gp.mutUniform``.  If the result exceeds *max_depth* the
    mutation is reverted.
    """
    idx = random.choice([0, 1])  # pick entry or exit
    original = list(individual[idx])
    individual[idx], = gp.mutUniform(individual[idx], expr=expr, pset=pset)
    if individual[idx].height > max_depth:
        del individual[idx][:]
        individual[idx].extend(original)
    return (individual,)


# ---------------------------------------------------------------------------
# Evaluation wrapper
# ---------------------------------------------------------------------------

def _eval_individual(
    individual,
    toolbox,
    df: pd.DataFrame,
    freq: str,
    init_cash: float,
    fees: float,
    complexity_penalty: float,
) -> tuple[float, ...]:
    """Evaluate a pair individual (entry_tree, exit_tree)."""
    entry_tree, exit_tree = individual[0], individual[1]
    return evaluate_pair(
        entry_tree, exit_tree, toolbox, df, freq,
        init_cash=init_cash, fees=fees,
        complexity_penalty=complexity_penalty,
    )


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_evolution(
    df_train: pd.DataFrame,
    freq: str,
    init_cash: float = 10_000,
    fees: float = 0.001,
    complexity_penalty: float = 0.01,
    max_depth: int = 8,
    seed: int = 42,
) -> tuple[Any, Any, Any, Any]:
    """Configure DEAP for GP evolution with entry/exit tree pairs.

    Returns:
        (toolbox, pset, stats, hof)
    """
    random.seed(seed)
    np.random.seed(seed)

    # Initialize context so ephemeral constants can access the index
    set_context(df_train)

    pset = create_pset()

    # --- Creator types ---
    if not hasattr(creator, "FitnessMax"):
        creator.create("FitnessMax", base.Fitness, weights=(1.0,))
    if not hasattr(creator, "EntryTree"):
        creator.create("EntryTree", gp.PrimitiveTree)
    if not hasattr(creator, "ExitTree"):
        creator.create("ExitTree", gp.PrimitiveTree)
    if not hasattr(creator, "Individual"):
        creator.create("Individual", list, fitness=creator.FitnessMax)
        # Individual = [EntryTree, ExitTree]

    # --- Toolbox ---
    toolbox = base.Toolbox()
    toolbox.register("expr", gp.genHalfAndHalf, pset=pset, min_=2, max_=5)
    toolbox.register("compile", gp.compile, pset=pset)

    # Individual creation: a pair of independently generated trees
    def _create_individual():
        entry = creator.EntryTree(toolbox.expr())
        exit_ = creator.ExitTree(toolbox.expr())
        ind = creator.Individual([entry, exit_])
        return ind

    toolbox.register("individual", _create_individual)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    # Fitness function (partial with fixed data)
    eval_fn = partial(
        _eval_individual,
        toolbox=toolbox, df=df_train, freq=freq,
        init_cash=init_cash, fees=fees,
        complexity_penalty=complexity_penalty,
    )
    toolbox.register("evaluate", eval_fn)

    # Selection
    toolbox.register(
        "select", selTournamentDiversity, tournsize=5, max_per_family=3,
    )

    # Mutation expression generator (used by _mutate_pair)
    toolbox.register("expr_mut", gp.genGrow, min_=1, max_=3)

    # Crossover and mutation with bloat control baked in
    toolbox.register("mate", _mate_pair, max_depth=max_depth)
    toolbox.register(
        "mutate", _mutate_pair,
        expr=toolbox.expr_mut, pset=pset, max_depth=max_depth,
    )

    # Stats
    stats = tools.Statistics(lambda ind: ind.fitness.values[0])
    stats.register("avg", lambda x: np.mean([v for v in x if v > -900]))
    stats.register("best", lambda x: np.max(x))
    stats.register("viable", lambda x: sum(1 for v in x if v > -900))

    # Hall of fame (custom implementation for pair individuals)
    hof = PairHallOfFame(maxsize=10)

    return toolbox, pset, stats, hof


# ---------------------------------------------------------------------------
# Evolution loop
# ---------------------------------------------------------------------------

def run_evolution(
    toolbox,
    stats,
    hof,
    pop_size: int = 100,
    n_gen: int = 20,
    cx_prob: float = 0.7,
    mut_prob: float = 0.2,
    verbose: bool = True,
) -> tuple[list, Any]:
    """Run the GP evolution loop for entry/exit tree pairs.

    Implements a manual generational loop (instead of ``eaSimple``)
    because DEAP's built-in algorithm does not handle list-based pair
    individuals correctly.

    Returns:
        (final_population, logbook)
    """
    pop = toolbox.population(n=pop_size)

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"  GP Evolution (pair mode) -- {pop_size} individuals x {n_gen} generations")
        print(f"  Crossover: {cx_prob:.0%} | Mutation: {mut_prob:.0%}")
        print(f"{'=' * 60}\n")

    # --- Evaluate initial population ---
    fitnesses = list(map(toolbox.evaluate, pop))
    for ind, fit in zip(pop, fitnesses):
        ind.fitness.values = fit

    logbook = tools.Logbook()
    logbook.header = ["gen", "nevals", "avg", "best", "viable"]

    fit_values = [ind.fitness.values[0] for ind in pop]
    record = stats.compile(pop)
    logbook.record(gen=0, nevals=len(pop), **record)
    if verbose:
        print(logbook.stream)

    hof.update(pop)

    # --- Generational loop ---
    for gen in range(1, n_gen + 1):
        # Selection
        offspring = toolbox.select(pop, len(pop))

        # Clone (deep copy so originals are not modified)
        offspring = [toolbox.clone(ind) for ind in offspring]

        # Crossover
        for i in range(1, len(offspring), 2):
            if random.random() < cx_prob:
                toolbox.mate(offspring[i - 1], offspring[i])
                del offspring[i - 1].fitness.values
                del offspring[i].fitness.values

        # Mutation
        for i in range(len(offspring)):
            if random.random() < mut_prob:
                toolbox.mutate(offspring[i])
                del offspring[i].fitness.values

        # Evaluate individuals with invalidated fitness
        invalids = [ind for ind in offspring if not ind.fitness.valid]
        fitnesses = list(map(toolbox.evaluate, invalids))
        for ind, fit in zip(invalids, fitnesses):
            ind.fitness.values = fit

        # Replace population
        pop[:] = offspring

        # Record statistics
        fit_values = [ind.fitness.values[0] for ind in pop]
        record = stats.compile(pop)
        logbook.record(gen=gen, nevals=len(invalids), **record)
        if verbose:
            print(logbook.stream)

        # Update hall of fame
        hof.update(pop)

    return pop, logbook


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_top_strategies(
    hof,
    toolbox,
    df_train: pd.DataFrame,
    df_test: pd.DataFrame,
    freq: str,
    init_cash: float = 10_000,
    fees: float = 0.001,
    top_n: int = 5,
) -> list[dict]:
    """Decode and validate the top pair strategies on both train and test sets.

    Returns a list of dicts with strategy details + in-sample /
    out-of-sample metrics.
    """
    results = []

    for i, ind in enumerate(hof[:top_n]):
        entry_tree, exit_tree = ind[0], ind[1]

        # In-sample
        set_context(df_train)
        train_info = decode_pair(
            entry_tree, exit_tree, toolbox, df_train, freq, init_cash, fees,
        )

        # Out-of-sample
        set_context(df_test)
        test_info = decode_pair(
            entry_tree, exit_tree, toolbox, df_test, freq, init_cash, fees,
        )

        results.append({
            "rank": i + 1,
            "entry_expression": str(entry_tree),
            "exit_expression": str(exit_tree),
            "entry_size": len(entry_tree),
            "exit_size": len(exit_tree),
            # In-sample
            "train_return": train_info.get("total_return", float("nan")),
            "train_sharpe": train_info.get("sharpe_ratio", float("nan")),
            "train_drawdown": train_info.get("max_drawdown", float("nan")),
            "train_trades": train_info.get("n_trades", 0),
            # Out-of-sample
            "test_return": test_info.get("total_return", float("nan")),
            "test_sharpe": test_info.get("sharpe_ratio", float("nan")),
            "test_drawdown": test_info.get("max_drawdown", float("nan")),
            "test_trades": test_info.get("n_trades", 0),
            # Keep full test result for plotting
            "test_portfolio": test_info.get("portfolio"),
            "test_entries": test_info.get("entries"),
            "test_exits": test_info.get("exits"),
            "test_price": test_info.get("price"),
        })

    return results
