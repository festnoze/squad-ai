"""CLI entry point for the money race.

Usage examples:
    python run_evolution.py
    python run_evolution.py --generations 200 --population 48 --seed 7
    python run_evolution.py --arenas auction,prediction --out results/no_market
    python run_evolution.py --llm-strategist   (needs the claude CLI, costs tokens)
"""

import argparse
import os
import random

from moneyrace import ledger, report
from moneyrace.arenas import ARENA_REGISTRY
from moneyrace.config import Config
from moneyrace.evolution import World


def parse_args():
    parser = argparse.ArgumentParser(description="Evolutionary money race harness")
    parser.add_argument("--population", type=int, default=32)
    parser.add_argument("--generations", type=int, default=80)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--arenas", default="auction,market,prediction",
                        help="comma-separated subset of: " + ",".join(ARENA_REGISTRY))
    parser.add_argument("--living-cost", type=float, default=4.0)
    parser.add_argument("--out", default=None,
                        help="output directory (default: results/run_s<seed>)")
    parser.add_argument("--log-every", type=int, default=10)
    parser.add_argument("--llm-strategist", action="store_true",
                        help="let the Claude CLI design a share of offspring genomes")
    return parser.parse_args()


def main():
    args = parse_args()
    arenas = tuple(name.strip() for name in args.arenas.split(",") if name.strip())
    unknown = [name for name in arenas if name not in ARENA_REGISTRY]
    if unknown:
        raise SystemExit(f"Unknown arenas: {unknown}. Available: {list(ARENA_REGISTRY)}")

    config = Config(population=args.population, generations=args.generations,
                    seed=args.seed, arenas=arenas, living_cost=args.living_cost)
    rng = random.Random(config.seed)

    strategist = None
    if args.llm_strategist:
        from moneyrace.llm_strategist import ClaudeStrategist
        strategist = ClaudeStrategist()
        if not strategist.available:
            print("warning: claude CLI not found, running without the strategist")
            strategist = None

    world = World(config, rng, strategist=strategist)
    for gen in range(config.generations):
        stats = world.step()
        if gen % args.log_every == 0 or gen == config.generations - 1:
            print(f"gen {stats['generation']:>4} | deaths {stats['deaths']:>2} "
                  f"| immigrants {stats['immigrants']:>2} "
                  f"| mean {stats['mean_wealth']:>9.1f} "
                  f"| max {stats['max_wealth']:>10.1f} "
                  f"| total {stats['total_wealth']:>11.1f}")

    leaderboard = world.leaderboard(top=10)
    out_dir = args.out or os.path.join("results", f"run_s{config.seed}")
    paths = ledger.write_run(out_dir, config, world.history, leaderboard, world.graveyard)
    report_path = os.path.join(out_dir, "report.html")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(report.render_report(config, world.history, leaderboard))

    print("\nTop agents:")
    for rank, entry in enumerate(leaderboard[:5], start=1):
        genes = " ".join(f"{k}={v:.2f}" for k, v in entry["genes"].items())
        print(f"  {rank}. agent #{entry['id']:<5} wealth {entry['wealth']:>10,.0f} "
              f"age {entry['age']:>3}  {genes}")
    if strategist is not None:
        print(f"\nLLM strategist: {strategist.successes}/{strategist.calls} "
              f"proposals accepted")
    print(f"\nOutputs: {paths['history']}, {paths['summary']}, {report_path}")


if __name__ == "__main__":
    main()
