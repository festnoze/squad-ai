# make_money - an evolutionary money race

A selection harness where a population of agents competes to make money in a
simulated economy. Money is not a proxy for fitness, it IS fitness:

- every generation, every agent burns a **living cost**; hit zero and you die
- agents earn (or lose) money in **arenas**: auctions, market trading, prediction bets
- empty population slots are refilled by reproduction, and parents are drawn
  with probability **proportional to their wealth**
- reproduction is not free: a parent **pays the child's endowment** out of its
  own wallet, so having kids is an economic decision
- a small **immigrant rate** injects fresh random genomes to keep diversity

Over generations, the gene pool drifts toward whatever actually makes money in
the current mix of arenas. Pure Python 3.9+, standard library only, fully
deterministic from a seed.

## Quickstart

```bash
cd make_money
python -m unittest              # run the test suite
python run_evolution.py         # default: 80 generations, population 32
```

Useful flags:

```bash
python run_evolution.py --generations 300 --population 48 --seed 7
python run_evolution.py --arenas auction,prediction --out results/no_market
python run_evolution.py --living-cost 8 --log-every 5
python run_evolution.py --llm-strategist    # see below, costs Claude tokens
```

Outputs land in `results/run_s<seed>/` (or `--out`):

- `history.jsonl` - one JSON row per generation (wealth stats, gene means, arena reports)
- `run.json` - config, final leaderboard, graveyard tail
- `report.html` - self-contained report: wealth curves, gene-mean drift
  (watch selection push genes over time), turnover chart, leaderboard table

## The arenas

All money flows are explicit and audited by the tests: each arena reports a
`system_delta` and the suite asserts it equals the actual total wealth change.

| Arena | Game | What evolution has to learn |
|---|---|---|
| `auction` | Sealed-bid second-price auctions on items of hidden value; every bidder sees a noisy appraisal | Bid shading vs the winner's curse, how much to trust a signal vs the prior |
| `market` | Trade a synthetic price series with random drift regimes (bull, flat, bear), fees on every position change | Balancing momentum vs mean-reversion, position sizing, not over-trading |
| `prediction` | Bet on binary events against a house that misprices them slightly; the house rakes 2% of winnings | Betting only when the edge beats a confidence threshold, stake sizing |

## The genome

Seven floats in [0, 1] (see `moneyrace/genome.py`): `risk`, `auction_shade`,
`signal_trust`, `momentum`, `reversion`, `trade_size`, `confidence`.
Children inherit a mutated copy of a parent's genome (gaussian mutation,
occasional gene reset, optional uniform crossover between two parents).
Decisions are made by `moneyrace/policy.py`, which maps genes onto actions
deterministically, so a whole run replays bit-identically from its seed.

## LLM strategist (optional)

`--llm-strategist` lets the Claude CLI (headless `claude -p`) design a share
of offspring genomes (`strategist_share`, default 25% of births) instead of
blind mutation: it sees the last five generations of stats plus a mutated
baseline and answers with a gene JSON. Any failure (no CLI, timeout, bad
output) silently falls back to normal mutation, so runs never block on the
LLM. It costs real tokens and real time; leave it off for big sweeps.

## Extending the race

Add an arena in `moneyrace/arenas.py`:

1. subclass `Arena`, set a `name`, implement `run(agents, rng)`
2. only touch wealth through `agent.credit(...)`
3. return `{"arena": self.name, "system_delta": <total money created>}`
4. register it in `ARENA_REGISTRY` and add an accounting test like the ones
   in `tests/test_arenas.py`

New behaviour usually also wants a gene: add it to `GENE_NAMES` and use it in
`GenomePolicy`. Old saved runs keep their meaning because genes are named.

## Design notes

- Money conservation: auction surplus (item value minus price paid), market
  P&L against the outside world, house rake, fees, living costs and immigrant
  endowments are the only sources and sinks; everything else is transfers.
- No arena can bankrupt an agent outright (losses are capped at allocated
  capital or stake), so death always comes from sustained underperformance
  against the living cost, which keeps selection gradual instead of noisy.
- Determinism: one `random.Random(seed)` drives everything, ids are allocated
  per-world, and there are no wall-clock or dict-order dependencies. Same
  seed plus same config gives an identical `history.jsonl`.
