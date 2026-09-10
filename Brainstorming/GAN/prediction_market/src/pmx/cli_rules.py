"""``pmx rules mine``, ``pmx rules test`` and ``pmx rules ledger`` (CONTRACTS_V2 18.2, package S2).

Three verbs, one subject: the hypothesis layer as a command. ``mine`` enumerates candidates on a fit fold
and writes them out, ``test`` puts a list of candidates through the whole procedure of 18.2 (fit screen,
pre-registration, the family's false discovery rate step, out-of-time replication, promotion, and on
request the live record and the transfer tests), and ``ledger`` renders what those runs wrote.

**Rows, not a dataset, for now.** A rule is evaluated on sensor blocks, and the blocks come from S1's
catalogue applied to the as-of views of a sealed dataset. Until ``pmx.sensors.catalogue`` ships, ``--rows``
takes a row table on disk (the shape ``tests/fixtures/s2/`` carries) and ``--dataset`` fails with a
``NotConfiguredError`` that names the missing package rather than an ``ImportError`` five frames down.
That is the same pattern ``pmx backtest`` used for A1's registry while wave 3 was being built, and it is
what lets this group parse its arguments, print its help and run against a fixture today.

``register`` exists so U4's ``pmx`` parser can mount the group in wave 5 without either file importing the
other's internals, and ``main`` exists so the group runs today as ``python -m pmx.cli_rules ...``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from pmx.errors import NotConfiguredError, PmxError
from pmx.journal import canonical_json
from pmx.rng import RngTree
from pmx.rules.miner import MinerResult, mine, template_of
from pmx.rules.rule import (
    RULE_MIN_SUPPORT_DEFAULT,
    Rule,
    RuleClaim,
    RuleScope,
    rule_from_dict,
)
from pmx.rules.tester import (
    FamilyTemplate,
    FoldPair,
    RowTable,
    RuleLedger,
    RuleTester,
    headline_pair,
    load_row_table,
    rolling_ks,
    rolling_pair,
)

__all__ = ["build_parser", "main", "register"]

#: Where a ledger is rooted when the caller says nothing: the repository the command runs in (9.5).
DEFAULT_ROOT = Path(".")


# --------------------------------------------------------------------------------------------------
# Shared arguments
# --------------------------------------------------------------------------------------------------
def _add_rows(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--rows", help="path to a row table JSON document (18.2's (market, bar) rows)")
    parser.add_argument(
        "--dataset", help="path to a sealed dataset (needs S1's sensor catalogue; not available yet)"
    )
    parser.add_argument("--rolling", type=int, default=None, help="the k of the rolling pair (12.7)")
    parser.add_argument(
        "--headline", action="store_true", help="use the (train, validation) pair instead of a rolling one"
    )


def _add_scope(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--kind", action="append", default=[], help="scope kind, repeatable")
    parser.add_argument("--provider", action="append", default=[], help="scope provider, repeatable")
    parser.add_argument("--category", action="append", default=[], help="scope category, repeatable")
    parser.add_argument("--tag", action="append", default=[], help="scope tag, repeatable")
    parser.add_argument("--cohort", action="append", default=[], help="scope cohort id, repeatable")


def _add_claim(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--claim", default="drift", choices=("bias", "drift", "volatility"))
    parser.add_argument("--direction", type=int, default=1, help="-1 or 1 on a bias or a drift, 0 otherwise")
    parser.add_argument("--magnitude-bp", type=int, default=100, help="the stated size of a bias or a drift")
    parser.add_argument("--factor-ppm", type=int, default=0, help="the stated excess of a volatility claim")
    parser.add_argument("--horizon-bars", type=int, default=1, help="0 on a bias, at least 1 otherwise")
    parser.add_argument("--min-support", type=int, default=RULE_MIN_SUPPORT_DEFAULT)


def _table(args: argparse.Namespace) -> RowTable:
    if args.dataset:
        raise NotConfiguredError(
            "building a row table from a dataset needs S1's sensor catalogue (pmx.sensors.catalogue) and "
            "FM1's feature matrix; pass --rows with a row table until they land",
            dataset=args.dataset,
        )
    if not args.rows:
        raise NotConfiguredError("pmx rules needs --rows (a row table) or --dataset")
    return load_row_table(Path(args.rows))


def _pair(table: RowTable, args: argparse.Namespace) -> FoldPair:
    if args.headline:
        return headline_pair(table)
    available = rolling_ks(table.split)
    k = args.rolling if args.rolling is not None else (available[-1] if available else None)
    if k is None:
        raise NotConfiguredError(
            "this dataset has no rolling pair inside its training fold (ruling R277); its remedy is 7.4's "
            "fallback order, never a silently narrower test",
            train_end_ms=table.split.train_end_ms,
        )
    return rolling_pair(table, int(k))


def _scope(args: argparse.Namespace) -> RuleScope:
    return RuleScope(
        kinds=tuple(sorted(set(args.kind))),
        providers=tuple(sorted(set(args.provider))),
        categories=tuple(sorted(set(args.category))),
        tags=tuple(sorted(set(args.tag))),
        cohorts=tuple(sorted(set(args.cohort))),
    )


def _claim(args: argparse.Namespace) -> RuleClaim:
    return RuleClaim(
        kind=args.claim,
        direction=args.direction if args.claim != "volatility" else 0,
        magnitude_bp=args.magnitude_bp if args.claim != "volatility" else 0,
        factor_ppm=args.factor_ppm if args.claim == "volatility" else 0,
    )


def _run_mine(table: RowTable, pair: FoldPair, args: argparse.Namespace) -> MinerResult:
    features = tuple(name.strip() for name in str(args.features).split(",") if name.strip())
    return mine(
        table,
        pair,
        scope=_scope(args),
        claim=_claim(args),
        horizon_bars=args.horizon_bars,
        features=features,
        min_support=args.min_support,
        beam=args.beam,
        candidates_max=args.max_candidates,
    )


# --------------------------------------------------------------------------------------------------
# pmx rules mine
# --------------------------------------------------------------------------------------------------
def _cmd_mine(args: argparse.Namespace) -> int:
    table = _table(args)
    pair = _pair(table, args)
    result = _run_mine(table, pair, args)
    print(
        f"mined {len(result.candidates)} candidates from {result.n_candidates} enumerated on "
        f"{pair.fit_fold} ({len(pair.fit_ids)} markets)" + (", truncated at the cap" if result.truncated else "")
    )
    for candidate in result.candidates[: args.limit]:
        condition = " and ".join(
            f"{predicate.feature} {predicate.op} {predicate.value}" for predicate in candidate.rule.condition
        )
        print(
            f"  {candidate.rule.rule_id}  lift {candidate.lift_bp:>7} bp  support {candidate.support:>5}  "
            f"markets {candidate.n_markets:>4}  {condition}"
        )
    if args.out:
        payload = {
            "dataset_hash": table.dataset_hash,
            "fit_fold": pair.fit_fold,
            "replicate_fold": pair.replicate_fold,
            "n_candidates": result.n_candidates,
            "template": result.template.to_dict(),
            "rules": [candidate.rule.to_dict() for candidate in result.candidates],
        }
        Path(args.out).write_text(canonical_json(payload) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


# --------------------------------------------------------------------------------------------------
# pmx rules test
# --------------------------------------------------------------------------------------------------
def _load_rules(path: Path) -> tuple[tuple[Rule, ...], FamilyTemplate | None, int | None]:
    """A miner output, a list of rule payloads, or one rule payload: all three are a candidate list."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(document, list):
        return tuple(rule_from_dict(entry) for entry in document), None, None
    rules = tuple(rule_from_dict(entry) for entry in document["rules"])
    template_payload = document.get("template")
    template = None
    if isinstance(template_payload, dict):
        template = FamilyTemplate(
            scope_keys=tuple(template_payload["scope_keys"]),
            features=tuple(template_payload["features"]),
            claim_kind=str(template_payload["claim_kind"]),
            horizon_bars=int(template_payload["horizon_bars"]),
            author_kind=str(template_payload["author_kind"]),
        )
    count = document.get("n_candidates")
    return rules, template, None if count is None else int(count)


def _cmd_test(args: argparse.Namespace) -> int:
    table = _table(args)
    pair = _pair(table, args)
    if args.rules:
        rules, template, n_candidates = _load_rules(Path(args.rules))
    else:
        result = _run_mine(table, pair, args)
        rules, template, n_candidates = result.rules(), result.template, result.n_candidates
    if args.top:
        rules = rules[: args.top]
    if template is None:
        template = template_of(
            _scope(args),
            sorted({predicate.feature for rule in rules for predicate in rule.condition}),
            _claim(args),
            args.horizon_bars,
        )
    ledger = RuleLedger(root=Path(args.ledger_root), dataset_hash=table.dataset_hash)
    tester = RuleTester(table, rng=RngTree(args.seed), ledger=ledger, generation=args.generation)
    fresh = [rule for rule in rules if not tester.is_duplicate(rule, pair)]
    skipped = len(rules) - len(fresh)
    if skipped:
        print(f"skipped {skipped} candidates already tested on ({pair.fit_fold}, {pair.replicate_fold})")
    if not fresh:
        print("nothing left to test")
        return 0
    outcome = tester.run_family(
        fresh, template=template, pair=pair, n_candidates=n_candidates or len(fresh)
    )
    family = outcome.family
    print(
        f"family {family.family_id} on ({family.fit_fold}, {family.replicate_fold}) "
        f"candidates {family.n_candidates} screened {family.n_screened} permutations {outcome.permutations}"
    )
    for record in outcome.replicate:
        print(
            f"  {record.rule_id}  lift {record.effect.point:>7} bp  lower {record.effect.lower:>7}  "
            f"support {record.support:>5}  p {record.p_value_ppm} ppm  fdr {record.fdr_k}/{record.fdr_m}  "
            f"{'promoted' if record.passed else 'rejected'}"
        )
    for promotion in outcome.promotions:
        print(f"  promoted {promotion.rule.rule_id} visible from {promotion.visible_from_ms}")
        if args.transfer:
            for record in tester.transfer_tests(promotion, pair):
                print(
                    f"    transfer {record.target}: support {record.support} lift {record.effect.point} "
                    f"{'holds' if record.passed else 'does not hold'}"
                )
        if args.live_at is not None:
            live = tester.live_record(promotion, pair, at_ms=int(args.live_at))
            print(
                f"    live [{live.from_ms}, {live.to_ms}): support {live.live_support} "
                f"lift {live.live_interval.point} lower {live.live_interval.lower}"
            )
            if live.demote:
                tester.demote(live, pair)
                print(f"    demoted: {live.reason}")
    print(f"ledger {ledger.rules_path}")
    return 0


# --------------------------------------------------------------------------------------------------
# pmx rules ledger
# --------------------------------------------------------------------------------------------------
def _proposals(runs: Path) -> tuple[dict[str, object], ...]:
    """The ``rule_proposed`` rows of the run journals under ``runs`` (ruling R294).

    The tester never writes one: that event has a single emitter, ``engine/runner.py``, and this verb
    copies its rows out of the journals rather than duplicating them into the ledger. The lines are read
    as JSON rather than through ``pmx.journal``'s reader because ``rule_proposed`` is declared and not yet
    in the catalogue (9.2), and a renderer that refused to show a declared event would be useless exactly
    while the event is new.
    """
    out: list[dict[str, object]] = []
    if not runs.is_dir():
        return ()
    for journal in sorted(runs.glob("*/journal.jsonl")):
        for line in journal.read_text(encoding="utf-8").splitlines():
            if '"rule_proposed"' not in line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict) and payload.get("type") == "rule_proposed":
                out.append(payload)
    return tuple(out)


def _cmd_ledger(args: argparse.Namespace) -> int:
    ledger = RuleLedger(root=Path(args.ledger_root), dataset_hash=args.dataset_hash)
    ledger.verify(ledger.families_path)
    ledger.verify(ledger.rules_path)
    families = ledger.families()
    rows = ledger.rules()
    print(f"{ledger.directory}: {len(families)} families, {len(rows)} rule rows")
    for family in families:
        print(
            f"  {family['family_id']}  ({family['fit_fold']}, {family['replicate_fold']})  "
            f"candidates {family['n_candidates']}  screened {family['n_screened']}"
        )
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("type"))
        if key == "rule_tested":
            key = f"rule_tested/{row.get('stage')}"
        counts[key] = counts.get(key, 0) + 1
    for key in sorted(counts):
        print(f"  {key}: {counts[key]}")
    for row in rows:
        if row.get("type") != "rule_promoted":
            continue
        print(f"  promoted {row['rule_id']} by {row['author_kind']} {row['author_id']}")
    if args.runs:
        proposals = _proposals(Path(args.runs))
        print(f"  rule_proposed rows in {args.runs}: {len(proposals)}")
        # 18.2: one rule, one statement, many proposers. The author of record is the first proposal in
        # journal order and the row counts how many times the same content was proposed.
        first: dict[str, dict[str, object]] = {}
        n_proposals: dict[str, int] = {}
        for payload in proposals:
            rule_id = str(payload.get("rule_id"))
            n_proposals[rule_id] = n_proposals.get(rule_id, 0) + 1
            first.setdefault(rule_id, payload)
        for rule_id in sorted(first)[: args.limit]:
            payload = first[rule_id]
            print(
                f"    {rule_id} first by {payload.get('agent_id')} at {payload.get('bar_ms')}, "
                f"n_proposals {n_proposals[rule_id]}"
            )
    return 0


# --------------------------------------------------------------------------------------------------
# The parser
# --------------------------------------------------------------------------------------------------
def build_parser(parser: argparse.ArgumentParser | None = None) -> argparse.ArgumentParser:
    parser = parser or argparse.ArgumentParser(prog="pmx rules")
    sub = parser.add_subparsers(dest="action", required=True)

    miner = sub.add_parser("mine", help="beam search for candidate rules on a fit fold")
    _add_rows(miner)
    _add_scope(miner)
    _add_claim(miner)
    miner.add_argument("--features", default="", help="comma separated feature names from the catalogue")
    miner.add_argument("--beam", type=int, default=32)
    miner.add_argument("--max-candidates", type=int, default=10_000)
    miner.add_argument("--limit", type=int, default=20)
    miner.add_argument("--out", default=None, help="write the candidates as a canonical JSON document")
    miner.set_defaults(func=_cmd_mine)

    tester = sub.add_parser("test", help="screen, pre-register, control the FDR, replicate and promote")
    _add_rows(tester)
    _add_scope(tester)
    _add_claim(tester)
    tester.add_argument("--rules", default=None, help="a miner output or a list of rule payloads")
    tester.add_argument("--features", default="", help="mine these features when --rules is not given")
    tester.add_argument("--beam", type=int, default=32)
    tester.add_argument("--max-candidates", type=int, default=10_000)
    tester.add_argument("--top", type=int, default=0, help="test only the first N candidates")
    tester.add_argument("--generation", type=int, default=0)
    tester.add_argument("--seed", type=int, default=1)
    tester.add_argument("--ledger-root", default=str(DEFAULT_ROOT))
    tester.add_argument("--transfer", action="store_true", help="re-test every promotion outside its scope")
    tester.add_argument("--live-at", type=int, default=None, help="recompute the live record as of this bar")
    tester.set_defaults(func=_cmd_test)

    renderer = sub.add_parser("ledger", help="render the rule ledger of a dataset")
    renderer.add_argument("--dataset-hash", required=True)
    renderer.add_argument("--ledger-root", default=str(DEFAULT_ROOT))
    renderer.add_argument("--runs", default=None, help="a runs/ directory whose rule_proposed rows to show")
    renderer.add_argument("--limit", type=int, default=20)
    renderer.set_defaults(func=_cmd_ledger)
    return parser


def _dispatch_group(args: argparse.Namespace) -> int:
    """What ``pmx rules`` alone does: nothing, loudly."""
    print("pmx rules needs a subcommand: mine, test, ledger")
    return 2


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Mount ``pmx rules`` on the top level parser (U4 calls this in wave 5)."""
    parser = subparsers.add_parser("rules", help="mine, test and render the hypothesis layer")
    build_parser(parser)
    parser.set_defaults(func=_dispatch_group)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the group as a program, which is how it is driven before U4 wires it into ``pmx``."""
    parser = argparse.ArgumentParser(
        prog="pmx rules",
        description="Mine, test and render the rules of the hypothesis layer (CONTRACTS_V2 18.2).",
    )
    build_parser(parser)
    args = parser.parse_args(list(argv) if argv is not None else None)
    handler = getattr(args, "func", None)
    if handler is None:  # pragma: no cover - the subparser is required
        parser.print_help()
        return 2
    try:
        return cast(Callable[[argparse.Namespace], int], handler)(args)
    except PmxError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - exercised through main() in the tests
    raise SystemExit(main())
