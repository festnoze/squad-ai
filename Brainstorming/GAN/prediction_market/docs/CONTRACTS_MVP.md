# pmx MVP: scoped contract amendment, 2026-09-13

## Discovery continuation

PLAN_DISCOVERY_MVP.md supersedes the fixed-strategy-only delivery scope below. It authorizes bounded
parameter and symbolic search, Polymarket archive ingestion, and campaign lifecycle endpoints. The
engine is version 2.2.1 and the contract revision is 2.2-discovery-mvp. Rule statistical certification
is still unavailable. One bootstrap block cannot support a positive promotion.

Markets may use currency `usdc` and optional `close_time_verified=false`. The latter means that the
technical close boundary is inferred, not a historically available expiry feature. It is hidden from
observations and calendar sensors. An archive first print becomes visible after its bar completes.
The optional `archive/` directory is part of the canonical dataset file inventory and hash.

POST /api/campaigns accepts dataset, provider, seed, n_trials (1..100), max_markets (6..200),
bankroll_cents (10000..100000000), n_splits (2..5) and finalists (1..5). It returns a persisted job.
GET /api/campaigns and GET /api/campaigns/{id} expose history and results; /export returns an attachment.
POST /api/jobs/{id}/cancel requests cooperative cancellation between evaluations. Public requests
cannot choose the sealed fold. Campaign and ordinary run jobs share one local worker.

Proposals are fit on an initial training prefix; parameters use later disjoint training windows.
Finalists are frozen before validation. Candidates need fills in every training window and at least
five distinct traded markets in total. Every parameter attempt and mined rule is recorded, including
rejects. Mining excludes zero-volume carried bars from support while retaining them in feature history.
Each period starts with fresh capital; returns use final marked equity. No cost-stress result or
statistical independence is claimed. The no-trade reference remains visible even if all trials lose.

## Decisions overriding the old delivery plan

- MVP-1: PLAN_MVP.md is the active delivery sequence under the user's explicit reprioritisation.
- MVP-2: The MVP is an exploratory binary backtest workbench. It exposes no certification, rule
  promotion, LLM, hive or evolution endpoint. Training and validation are the only runnable slices.
  The sealed slice is not exposed by the MVP market browser or run API.
- MVP-3: A derivative named mvp2026 may be rebuilt entirely from the existing y2026 market/news files,
  with corrected folds and taxonomy, using the existing builder and verifier. Original data stays
  unchanged. Record the source dataset hash and the historical snapshot's limitations. A coverage
  shortfall stays recorded; it does not prevent exploratory runs and never becomes a passed claim.
- MVP-4: Three fixed genuine strategies are enough: follower (market probability, no trades), trend
  (bounded recent-move extrapolation), revert (bounded recent-mean reversion). A fourth fixed strategy
  is optional. Parameters and descriptions are returned by the registry. No test stubs or v1 engine
  are used by the MVP. Agents can be constructed by the existing cli_run registry interface.
- MVP-5: Run identity must include the sorted population's agent IDs and serialized genomes. This
  correctness change may ship with its own engine version bump; it no longer waits for every R274
  schema addition. Other deferred shapes stay documented, not silently marked implemented.
- MVP-6: Past rule records may include only targets whose results are available at the record time.
  Bias targets require resolution; drift/volatility require the horizon bar to be completed. A
  future-result mutation must not change the earlier record. Rule trading is still deferred.
- MVP-7: Runs use one provider, one fold and a deterministic bounded market selection, default 12,
  maximum 30. Include the actual selected IDs in the result. No population-level optimization occurs.
  Shared simulated liquidity is explicitly described in the run limitations.
- MVP-8: UI metrics are exploratory point estimates. Uncertainty may be reported only when
  estimable; do not call a degenerate interval evidence. No positive result is labelled certified.
- MVP-9: The API binds to loopback by default. One background worker serializes runs; requests receive
  a job ID immediately. Job failures are visible, history survives reload, and duplicates do not
  overwrite a different experiment. Do not accept arbitrary paths or module names from HTTP.
- MVP-10: Technical correctness gates remain. A change to an obsolete contract assertion must be
  accompanied by this amendment and meaningful behavioural evidence, not a weaker assertion.

## HTTP contract shared by frontend and backend

All endpoints are under /api. JSON numbers below are integers unless explicitly marked otherwise.
Timestamps are UTC milliseconds; prices are basis points (10000 is a one-unit binary payout),
probabilities are ppm, Brier/skill are micro-units, money is cents of the displayed provider currency.
Errors use a JSON detail string. Dataset names, run IDs and job IDs are validated identifiers.

### Dataset and market catalogue

- GET /api/health -> {status: "ok", dataset_available: boolean}
- GET /api/datasets -> {datasets: DatasetSummary[]}
- GET /api/datasets/{name} -> DatasetSummary
- GET /api/datasets/{name}/markets?provider=kalshi&fold=validation&category=&q=&page=1&page_size=25
  -> {items: MarketSummary[], total, page, page_size}
  The provider, fold, category and q filters are optional. Never return sealed-slice markets.
- GET /api/datasets/{name}/markets/{market_id} ->
  {market: MarketSummary, bars: Bar[], news: NewsSummary[]}

DatasetSummary = {name, dataset_hash, freeze_date, interval_min, n_markets, n_visible_markets,
  providers: string[], categories: string[], counts_by_provider: Record<string, number>,
  counts_by_fold: Record<string, number>, limitations: string[]}
MarketSummary = {id, question, category, provider, currency, fold, source, created_at_ms, close_at_ms,
  resolved_at_ms, resolution: 0|1, n_bars, n_trades, volume_milli, subjects: string[], structure,
  horizon, cohort_id: string|null}
Bar = {t_ms, open_bp, high_bp, low_bp, close_bp, volume_milli}
NewsSummary = {id, published_at_ms, visible_from_ms, source, text, url}

### Strategies and execution

- GET /api/agents -> {agents: AgentSummary[]}
  AgentSummary = {id, name, description, baseline: boolean, parameters: Record<string, number>}
- POST /api/runs accepts {dataset: "mvp2026", provider: "kalshi"|"manifold",
  fold: "train"|"validation", agent_ids: string[], seed: number, bankroll_cents: number,
  max_markets: number}. Defaults: validation, all fixed agents, seed 7, bankroll 100000, 12 markets.
  -> Job, HTTP 202. Reject unknown agents, duplicate/empty agents, unavailable datasets/providers,
  sealed, invalid bounds and concurrent submissions when capacity is exhausted, with useful errors.
- GET /api/jobs/{job_id} -> Job
  Job = {job_id, status: "queued"|"running"|"completed"|"failed", run_id: string|null,
  error: string|null}
- GET /api/runs -> {runs: RunSummary[]}, newest first
- GET /api/runs/{run_id} -> RunDetail
- GET /api/runs/{run_id}/markets/{market_id} -> RunMarketReplay
- GET /api/runs/{run_id}/export and GET /api/runs/{run_id}/markets/{market_id}/export
  return the same JSON with an attachment header for reliable browser downloads.

RunSummary = {run_id, dataset, dataset_hash, provider, currency, fold, seed, bankroll_cents,
  market_ids: string[], agent_ids: string[], n_markets, journal_hash, created_at: string,
  status: "completed", limitations: string[]}
RunDetail = {run: RunSummary, leaderboard: AgentResult[], equity: EquityPoint[],
  markets: MarketSummary[]}
AgentResult = {agent_id, name, baseline, n_markets, mean_brier_micro, market_brier_micro,
  skill_micro, pnl_cents, fees_cents, n_fills, max_drawdown_bp, final_equity_cents}
EquityPoint = {t_ms, agents: Record<string, number>} (per-agent marked equity in cents)
RunMarketReplay = {market_id, agent_ids: string[], ticks: ReplayTick[], fills: ReplayFill[]}
ReplayTick = {t_ms, price_bp, agents: Record<string, {prob_ppm, position, equity_cents}>}
ReplayFill = {t_ms, agent_id, side, size, price_bp, fee_cents}

The backend derives metrics and replay from v2 projection/journal events, not an independent trading
simulation. API lifecycle timestamps stay outside deterministic journals. Detail exports may use the
ordinary GET response downloaded by the browser. All payload changes require coordinator notification.

## Execution and release notes

R1 adds `GET /api/signal-studies/protocol`, `GET/POST /api/signal-studies` (strict body `{dataset}`),
`GET /api/signal-studies/{id}`, and completed-result `/export` and `/observations` downloads. Its fixed
`signal-study.v1` protocol is written before a separate bounded worker loads the dataset. Identity
includes dataset hash, protocol and verified historical sealed-ID protection. Cache hits reuse results;
failed/interrupted jobs require explicit retry. No study calls a validation/sealed market accessor,
no strategy is optimized, and no statistical certification is produced. The canonical loader's global
structural and hash checks remain distinct from analytical access to training observations.

The first observation per market/variant precedes activity filtering and target-availability checks.
Missing targets remain counted, never moved to another observation. Source, midpoint and reversal
endpoint prices require observed transactions; future targets require exact timestamps. Calibration
labels are exposed only after their settlement bar and strictly before the effective training cutoff.
The 28 variants, nested activity conditions and unadjusted descriptive intervals remain explicit.

Frontend charts compare capital, initial-capital return and running-peak drawdown. Time axes use actual
UTC timestamps, not evenly spaced row numbers. Curves preserve missing boundaries and never extend a
candidate past its recorded period. Independent finalist curves require matching dataset identity,
currency, capital, validation dates and market universe. Raw observations remain downloadable.

Post-campaign interpretation is an optional application/CLI service, outside the deterministic engine.
`GET/POST /api/analysis/settings` reads/sets `{enabled: boolean}` (strict boolean). Completion enqueues
an analysis only when enabled. `GET/POST /api/campaigns/{id}/analysis` returns/requests its persistent
state; repeated completed requests reuse the campaign/version fingerprint. Failed or interrupted
attempts do not retry automatically. `GET .../analysis/export` downloads Markdown and
`GET .../analysis/evidence` downloads the frozen JSON evidence packet. States are `not_requested`,
`queued`, `running`, `completed`, `failed`. Analysis errors never rewrite campaign results.

One separate review worker calls official local `codex exec` using verified ChatGPT login, with no
API-key fallback. An inference lasts at most 240 seconds after a 20-second login check. Evidence
excludes sealed tapes, retains missingness and distinguishes fixed-fill fee add-back from a new
simulation. The validated French response contains summary, verdict, findings, next tests and limits;
proposals are never executed automatically. Settings, attempts, evidence hashes and reports survive
restart. One process owns a runs directory; multi-process coordination is outside this local MVP.

`discovery.v2` fixes binary drift-target horizons on sparse/sampled mining rows: the target must exist
at `source_time + horizon * interval`, never merely at the next retained row. Missing target means no
available target. Continuous assets retain trading-bar semantics. Historical `discovery.v1` campaign
artifacts remain intact and receive an integrity note in their interpretation packet.

Discovery compatibility correction: `market_listed.symbol` permits 1..128 characters when `kind` is
`binary`, matching the already accepted `market.provider_id` it carries verbatim. This admits Polygon's
66-character condition IDs. Continuous symbols retain their 1..64 bound. Only reader validation changes;
no event bytes, identifiers, execution calculations or stored journal hashes change.

The existing financial execution model is a research approximation. The MVP does not claim that
historical bar volume proves order book availability. The interface must show daily-grid latency,
provider currency, the selected sample, and exploratory status without obscuring the actual results.
No manufactured human audit verdicts or successful economic claims are created during the build.

Frontend and backend are served locally, preferably from the same server after a production build.
The development server proxies /api to 127.0.0.1:8175. The local launcher must avoid spawning visible
helper windows. A running application, a repeatable CLI path and browser verification close M4.
