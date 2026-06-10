"""
Optuna-based hyperparameter optimizer for GP evolution.

Instead of manually guessing GP hyperparameters (pop_size, n_gen, max_depth,
etc.), this module uses Optuna's TPE sampler to search for the configuration
that produces the best out-of-sample Sharpe ratio across short GP runs.

Usage::

    from src.agent.optimizer import optimize_gp_hyperparams

    result = optimize_gp_hyperparams(df_train, df_test, freq="1d", n_trials=20)
    print(result["best_params"])
    print(result["best_score"])
"""

from __future__ import annotations

import math
import time
from functools import partial
from typing import Any

import pandas as pd
import optuna

from src.agent.evolution import (
    setup_evolution,
    run_evolution,
    validate_top_strategies,
)
from src.agent.fitness import evaluate_pair


# ---------------------------------------------------------------------------
# Internal: evaluation wrapper with configurable n_splits
# ---------------------------------------------------------------------------

def _eval_individual_with_splits(
    individual,
    *,
    toolbox,
    df: pd.DataFrame,
    freq: str,
    init_cash: float,
    fees: float,
    complexity_penalty: float,
    n_splits: int,
) -> tuple[float, ...]:
    """Evaluate a pair individual using a specific number of walk-forward splits.

    This thin wrapper unpacks the individual's entry/exit trees and delegates
    to :func:`evaluate_pair` with the caller-specified ``n_splits``.
    """
    entry_tree, exit_tree = individual[0], individual[1]
    return evaluate_pair(
        entry_tree,
        exit_tree,
        toolbox,
        df,
        freq,
        init_cash=init_cash,
        fees=fees,
        complexity_penalty=complexity_penalty,
        n_splits=n_splits,
    )


# ---------------------------------------------------------------------------
# Objective function
# ---------------------------------------------------------------------------

def _objective(
    trial: optuna.Trial,
    df_train: pd.DataFrame,
    df_test: pd.DataFrame,
    freq: str,
    seed: int,
) -> float:
    """Optuna objective: run a short GP evolution and return the test Sharpe.

    Samples hyperparameters from the search space, runs a full
    setup -> evolve -> validate cycle, and returns the out-of-sample
    Sharpe ratio of the best strategy found.  Returns -999 when the
    evolution produces no viable strategies.
    """
    # --- Sample hyperparameters ---
    pop_size = trial.suggest_int("pop_size", 50, 300, step=50)
    n_gen = trial.suggest_int("n_gen", 10, 50, step=5)
    max_depth = trial.suggest_int("max_depth", 4, 8)
    complexity_penalty = trial.suggest_float(
        "complexity_penalty", 0.01, 0.10, step=0.01,
    )
    cx_prob = trial.suggest_float("cx_prob", 0.5, 0.9, step=0.1)
    mut_prob = trial.suggest_float("mut_prob", 0.1, 0.4, step=0.05)
    n_splits = trial.suggest_int("n_splits", 2, 5)

    try:
        # 1. Setup evolution with trial-specific seed
        trial_seed = seed + trial.number
        toolbox, pset, stats, hof = setup_evolution(
            df_train,
            freq,
            complexity_penalty=complexity_penalty,
            max_depth=max_depth,
            seed=trial_seed,
        )

        # 2. Re-register the evaluate function with the trial's n_splits
        eval_fn = partial(
            _eval_individual_with_splits,
            toolbox=toolbox,
            df=df_train,
            freq=freq,
            init_cash=10_000,
            fees=0.001,
            complexity_penalty=complexity_penalty,
            n_splits=n_splits,
        )
        toolbox.register("evaluate", eval_fn)

        # 3. Run evolution (silently)
        run_evolution(
            toolbox,
            stats,
            hof,
            pop_size=pop_size,
            n_gen=n_gen,
            cx_prob=cx_prob,
            mut_prob=mut_prob,
            verbose=False,
        )

        # 4. Validate the best strategy on the test set
        if len(hof) == 0:
            return -999.0

        validation = validate_top_strategies(
            hof, toolbox, df_train, df_test, freq, top_n=1,
        )

        if not validation:
            return -999.0

        best = validation[0]
        test_sharpe = best.get("test_sharpe", float("nan"))

        if math.isnan(test_sharpe) or math.isinf(test_sharpe):
            return -999.0

        return float(test_sharpe)

    except Exception:
        return -999.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def optimize_gp_hyperparams(
    df_train: pd.DataFrame,
    df_test: pd.DataFrame,
    freq: str,
    n_trials: int = 20,
    n_jobs: int = 1,
    seed: int = 42,
    callback: callable | None = None,
) -> dict[str, Any]:
    """Find optimal GP hyperparameters via Optuna's TPE sampler.

    Runs *n_trials* short GP evolutions, each with a different set of
    hyperparameters sampled by Optuna.  The objective is the out-of-sample
    Sharpe ratio of the best strategy produced by each evolution.

    Args:
        df_train: OHLCV training data (used for GP evolution).
        df_test: OHLCV test data (used for OOS validation).
        freq: VectorBT frequency string (e.g. ``"1d"``).
        n_trials: Number of Optuna trials to run.
        n_jobs: Parallelism for Optuna (1 = sequential).
        seed: Random seed for reproducibility.
        callback: Optional callable ``(trial_number, params, score)``
            invoked after each completed trial.

    Returns:
        Dict with keys:

        - ``best_params``: optimal hyperparameter dict
        - ``best_score``: best OOS test Sharpe
        - ``best_strategy``: strategy details from the best trial
        - ``all_trials``: list of per-trial records
        - ``study_stats``: summary statistics of the optimization run
    """
    # Suppress noisy Optuna logs
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )

    # Track per-trial results for the return payload
    all_trials: list[dict[str, Any]] = []

    def _wrapped_objective(trial: optuna.Trial) -> float:

        score = _objective(trial, df_train, df_test, freq, seed)

        # Record trial
        trial_record = {
            "trial_number": trial.number,
            "params": dict(trial.params),
            "score": score,
            "status": "complete" if score > -999 else "failed",
        }
        all_trials.append(trial_record)

        # Print one-line summary or invoke callback
        if callback is not None:
            callback(trial.number, dict(trial.params), score)
        else:
            p = trial.params
            print(
                f"Trial {trial.number}: "
                f"pop={p.get('pop_size')} "
                f"gen={p.get('n_gen')} "
                f"depth={p.get('max_depth')} "
                f"penalty={p.get('complexity_penalty', 0):.2f} "
                f"-> test_sharpe={score:.3f}"
            )

        return score

    t_start = time.time()
    study.optimize(_wrapped_objective, n_trials=n_trials, n_jobs=n_jobs)
    t_elapsed = time.time() - t_start

    # --- Reconstruct the best strategy details ---
    best_strategy: dict[str, Any] = {}

    if study.best_trial is not None and study.best_value > -999:
        best_params = dict(study.best_params)

        # Re-run the best configuration to capture strategy details
        try:
            trial_seed = seed + study.best_trial.number
            toolbox, pset, stats, hof = setup_evolution(
                df_train,
                freq,
                complexity_penalty=best_params["complexity_penalty"],
                max_depth=best_params["max_depth"],
                seed=trial_seed,
            )

            # Re-register evaluate with the best n_splits
            eval_fn = partial(
                _eval_individual_with_splits,
                toolbox=toolbox,
                df=df_train,
                freq=freq,
                init_cash=10_000,
                fees=0.001,
                complexity_penalty=best_params["complexity_penalty"],
                n_splits=best_params["n_splits"],
            )
            toolbox.register("evaluate", eval_fn)

            run_evolution(
                toolbox,
                stats,
                hof,
                pop_size=best_params["pop_size"],
                n_gen=best_params["n_gen"],
                cx_prob=best_params["cx_prob"],
                mut_prob=best_params["mut_prob"],
                verbose=False,
            )

            if len(hof) > 0:
                validation = validate_top_strategies(
                    hof, toolbox, df_train, df_test, freq, top_n=1,
                )
                if validation:
                    v = validation[0]
                    best_strategy = {
                        "entry_expression": v.get("entry_expression", ""),
                        "exit_expression": v.get("exit_expression", ""),
                        "train_sharpe": v.get("train_sharpe", float("nan")),
                        "test_sharpe": v.get("test_sharpe", float("nan")),
                        "train_return": v.get("train_return", float("nan")),
                        "test_return": v.get("test_return", float("nan")),
                        "train_drawdown": v.get("train_drawdown", float("nan")),
                        "test_drawdown": v.get("test_drawdown", float("nan")),
                        "train_trades": v.get("train_trades", 0),
                        "test_trades": v.get("test_trades", 0),
                    }
        except Exception:
            pass  # best_strategy stays empty; score is still valid

        best_score = study.best_value
    else:
        best_params = {}
        best_score = -999.0

    # --- Compile study statistics ---
    n_complete = sum(1 for t in all_trials if t["status"] == "complete")
    n_failed = sum(1 for t in all_trials if t["status"] == "failed")

    study_stats = {
        "n_trials": len(all_trials),
        "n_complete": n_complete,
        "n_pruned": n_failed,
        "best_trial_number": (
            study.best_trial.number if study.best_trial is not None else -1
        ),
        "optimization_time_seconds": round(t_elapsed, 2),
    }

    return {
        "best_params": best_params,
        "best_score": best_score,
        "best_strategy": best_strategy,
        "all_trials": all_trials,
        "study_stats": study_stats,
    }
