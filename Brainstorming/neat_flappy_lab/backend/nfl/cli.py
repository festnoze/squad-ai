"""Headless driver — run the engine without the frontend.

Validates the whole pipeline from the terminal and lets you compare regimes:

    uv run nfl --mode evolution_only --generations 50
    uv run nfl --mode write_back --generations 50 --seed 1

Prints per-generation fitness/species/complexity and reports the generation at
which a fitness threshold ("solved") is first reached.
"""

from __future__ import annotations

import argparse

from .config import Activation, Mode, SimConfig, TeacherScope
from .engine.runner import Runner


def build_config(args: argparse.Namespace) -> SimConfig:
    overrides: dict = {
        "mode": Mode(args.mode),
        "pop_size": args.pop_size,
        "seed": args.seed,
        "gd_steps": args.gd_steps,
        "gd_lr": args.gd_lr,
        "teacher_k": args.teacher_k,
        "initial_hidden": args.initial_hidden,
        "max_ticks_per_gen": args.max_ticks,
        "activation": Activation(args.activation),
        "gd_ratio": args.gd_ratio,
        "gd_teacher_scope": TeacherScope(args.gd_teacher_scope),
    }
    return SimConfig(**overrides)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nfl", description="NEAT Flappy Lab — headless runner")
    parser.add_argument(
        "--mode",
        choices=[m.value for m in Mode],
        default=Mode.evolution_only.value,
        help="Hybridization regime.",
    )
    parser.add_argument("--generations", type=int, default=50, help="Generations to run.")
    parser.add_argument("--pop-size", type=int, default=120, help="Population size.")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed.")
    parser.add_argument("--gd-steps", type=int, default=8, help="GD steps per agent per gen.")
    parser.add_argument("--gd-lr", type=float, default=0.05, help="GD learning rate.")
    parser.add_argument("--teacher-k", type=int, default=3, help="Top-K imitation teachers.")
    parser.add_argument("--initial-hidden", type=int, default=0, help="Hidden nodes at birth.")
    parser.add_argument("--max-ticks", type=int, default=2000, help="Max ticks per generation.")
    parser.add_argument(
        "--activation",
        choices=[a.value for a in Activation],
        default=Activation.tanh.value,
        help="Hidden/output activation.",
    )
    parser.add_argument(
        "--gd-ratio",
        type=float,
        default=0.5,
        help="Confrontation mode: fraction of the population in the GD camp.",
    )
    parser.add_argument(
        "--gd-teacher-scope",
        choices=[t.value for t in TeacherScope],
        default=TeacherScope.camp.value,
        help="Confrontation mode: GD camp imitates its own champions or the global ones.",
    )
    parser.add_argument(
        "--solve-threshold",
        type=float,
        default=15.0,
        help="Fitness considered 'solved' (≈ pipes cleared).",
    )
    args = parser.parse_args(argv)

    config = build_config(args)
    runner = Runner(config)

    print(
        f"mode={config.mode.value} pop={config.pop_size} seed={config.seed} "
        f"sensors={len(config.active_sensors)} gd_steps={config.gd_steps} "
        f"activation={config.activation.value}"
    )
    confrontation = config.mode == Mode.confrontation
    camp_cols = f" {'neat max':>9} {'gd max':>9}" if confrontation else ""
    print(f"{'gen':>4} {'max':>8} {'mean':>8} {'species':>8} {'complexity':>11}{camp_cols}")

    solved_at: int | None = None
    wins = {"neat": 0, "gd": 0}
    for _ in range(args.generations):
        stats = runner.step_generation()
        line = (
            f"{stats['gen']:>4} {stats['fitnessMax']:>8.2f} {stats['fitnessMean']:>8.2f} "
            f"{stats['species']:>8} {stats['complexity']:>11.2f}"
        )
        if confrontation:
            camps = stats.get("camps", {})
            neat_max = camps.get("neat", {}).get("fitnessMax", float("nan"))
            gd_max = camps.get("gd", {}).get("fitnessMax", float("nan"))
            line += f" {neat_max:>9.2f} {gd_max:>9.2f}"
            winner = str(stats.get("winnerCamp", ""))
            if winner in wins:
                wins[winner] += 1
        print(line)
        if solved_at is None and stats["fitnessMax"] >= args.solve_threshold:
            solved_at = stats["gen"]

    if confrontation:
        print(f"\nGenerations won — NEAT: {wins['neat']}  GD: {wins['gd']}")
    if solved_at is not None:
        print(f"\nSOLVED at generation {solved_at} (fitness >= {args.solve_threshold}).")
    else:
        print(f"\nNot solved within {args.generations} generations (threshold {args.solve_threshold}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
