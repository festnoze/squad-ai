# Real-world arenas: ideas that score against actual data

**Goal.** Find the best agent / skill / prompt for a problem, using coop or selection, where the
*world* provides the score, not an LLM judge. Paper money first, a credible path to real money later.

## The one principle that ranks everything

The only arenas worth building are ones with **clean, cheap, fast, non-gameable ground truth**. That
is exactly Exchange's founding rule ("no metric depends on an LLM judge") pointed at reality instead of
a simulated world. Rank every candidate on four axes:

- **Truth quality**: is the label unarguable (an event resolved, a number printed) or fuzzy?
- **Feedback speed**: how long until you learn whether an agent was right? This sets how fast selection converges.
- **Data cost / legality**: free and clean, or scraped and fragile?
- **Money path**: can the exact same loop run on a small live account with no redesign?

Two mechanics, pick per problem:

- **Selection** (survival of the fittest): many agents, the world pays them, the worst are culled, the
  best are cloned with prompt mutation. Best when feedback is fast and you want to *discover* a strategy.
  This is the `make_maney` and AllAllowed loop.
- **Coop** (aggregation / ensemble): agents forecast independently, you learn *which* to trust and how
  to combine them. Best when the truth is slow but clean, and diversity beats any single agent. This is
  the wisdom-of-crowds question, and it is where LLM prompt diversity actually pays.

## The five, ranked

### 1. Shadow book on real prediction markets (Polymarket / Kalshi)  ★ best overall

Point Exchange at a live market instead of its simulated CLOB. Each open contract is a question with a
free, continuously-updated market probability; **resolution is clean binary truth**. Paper: log your
fill at the quoted price, settle on resolution, score Brier + PnL against the market. This reuses
Exchange's calibration and performance metrics almost unchanged.

- Truth: excellent (events resolve). Feedback: hours to weeks. Data: free public APIs. Money: trivial, a small real account runs the identical loop.
- **The real question is coop**: does an ensemble of diverse LLM-forecaster prompts, selected and
  weighted by past calibration, beat the market's own price? That is publishable and monetizable.
- Risk: markets are near-efficient, so beating them is the whole hard part; measure edge *after* fees
  and only on the held-out event set (Exchange already has the held-out bank for exactly this).

### 2. Closing-line-value league on sports odds  ★ best feedback loop

Bet (on paper) at the opening line, then measure **closing-line value**: did the market move toward
your side before the game even starts? CLV is a proven skill proxy that gives a signal on *every* game,
long before it resolves, so selection converges fast and cheap. The game outcome is the final,
unarguable label.

- Truth: excellent. Feedback: same day, plus an early CLV signal within hours. Data: free odds APIs. Money: real sportsbooks, though ToS and limits are a real constraint.
- Best fit for **selection**: the fast signal is what makes a cull-and-clone tournament actually work.
- Risk: books limit winners; treat it as a research testbed for the selection machinery more than a business.

### 3. Crypto walk-forward trading league  ★ best money realism

Free 24/7 OHLCV, exchange **testnets** for genuine paper fills, a tiny live account for real. Agents
are strategy archetypes (or LLM-authored strategies); the world pays realized PnL after costs. Selection
is MAP-Elites over the strategy space, which `make_maney` already prototypes.

- Truth: good (PnL is real) but noisy. Feedback: minutes to days. Data: free. Money: direct, same loop on a live key.
- Best fit for **selection with strict discipline**: walk-forward only, transaction costs mandatory,
  held-out time windows. Your determinism and no-float-in-money habits are precisely what keeps this honest.
- Risk: overfitting to noise is the default outcome; most "winning" agents are luck. The held-out bank
  and integrity detectors are the antidote, and proving an edge is *fake* is itself a valid result.

### 4. Economic-data nowcasting  ★ cleanest truth

Forecast the next official print: CPI, non-farm payrolls, an earnings number, a weather value. The
released figure is **truth with zero ambiguity**. Kalshi lists matching contracts, so there is a money
path bolted straight onto the ground truth.

- Truth: perfect. Feedback: slow (weekly / monthly). Data: free official releases. Money: via the matching contract.
- Best fit for **coop / calibration**: with slow feedback you cannot cull fast, so the win is
  aggregating diverse forecaster prompts and learning whose calibration to trust. Directly reuses
  Exchange's Brier scoring.
- Risk: slow loop; you need many parallel questions to get enough labels to select on.

### 5. The prompt-bakeoff factory (the meta-tool)  ★ most general, most sellable

Not a market: the generalization of all of the above. Any problem with a historical labeled dataset
(churn, demand, fraud, lead scoring, LTV) becomes an arena where LLM agents propose features, prompts,
or whole pipelines, and **walk-forward accuracy on held-out real data is the scorer**. This is literally
"find the best agent / skill / prompt for a given problem" turned into a product.

- Truth: excellent (held-out labels). Feedback: as fast as a backtest. Data: the client's own. Money: sell the winning model, the signal, or the factory itself.
- Fits **both**: selection to breed the best pipeline, coop to ensemble the top survivors.
- Risk: data-snooping and leakage; the discipline is a sealed test set touched once, which Exchange's
  held-out bank already enforces as a logged, refused-on-reuse resource.

## My recommendation

Build **#1 (prediction-market shadow book)** first. It is the smallest step from what already exists in
Exchange (same Brier + PnL, same held-out bank, swap the simulated CLOB for a real feed), it has the
cleanest truth of any money-bearing arena, and its central question (can selected, aggregated LLM
forecasters beat the market) is genuinely open. Prove the loop end to end on paper, on the sealed event
set, after fees. Then **#5** is where the money is: the same walk-forward-scored selection engine, sold
as a way to find the best pipeline for any client's labeled problem.

Everything here stays honest for one reason: the score is a fact about the world, logged before
resolution and never editable after. That is the Exchange rule, and it is the only thing that separates
a real edge from a story an agent tells about itself.
