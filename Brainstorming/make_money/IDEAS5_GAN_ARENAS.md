# Agent-Driven Income Ideas, Part 5: GAN-style arenas that optimize a metric worth money

Research date: 6 September 2026. Builds on the arenas in `../GAN/` (AllAllowed, Helios Vault,
Exchange, pmx) and on [`../GAN/docs/REAL_WORLD_ARENAS.md`](../GAN/docs/REAL_WORLD_ARENAS.md),
which already covers prediction markets, sports closing-line value, crypto walk-forward,
economic nowcasting and the prompt-bakeoff factory. None of those five is repeated here.

## What "GAN agents" means in this repo, and what stays fixed

The four existing arenas share one architecture, and every idea below keeps it:

- **The world is the only referee.** A deterministic engine computes the score; no metric
  depends on an LLM judge (Exchange rule FR-5.1.2, pmx "reality is the referee").
- **Event-sourced journal.** Every match replays bit for bit from its journal; metrics are
  projections of the journal, never stored opinions.
- **Sealed held-out bank.** Selection happens on one set, the claim is graded on another
  that is logged and refused on reuse (Exchange held-out bank, pmx walk-forward).
- **Three mechanics.** *Selection* (cull the worst, clone the best with mutation, the
  AllAllowed and make_money loop), *co-evolution* (a generator against a discriminator, the
  literal GAN), and *coop* (independent agents, learn whom to trust and how to weight them).
- **Integrity detectors.** AllAllowed exists to show agents will forge the rubric, raid the
  scorer, or free-ride; every real arena needs the same detectors pointed at Goodhart.

What changes: the score is a number someone already pays for. The ranking below uses the
four axes from REAL_WORLD_ARENAS.md (truth quality, feedback speed, data cost and legality,
money path) plus a fifth that the real world forces: **gameability**, meaning how easily a
selected agent wins the metric while destroying the thing the metric stood for. The arenas
that survive are the ones where the metric and the value are the same object.

Scores keep the IDEAS_RANKING.md scale: realism 1 to 5, ease 1 to 5, EUR per month at
month 6 for a solo operator.

---

## Family A: co-evolution (a real GAN: attacker versus defender)

### 1. Prompt-injection red team versus blue team
- **Metric**: attack success rate of injected instructions against a defended agent, measured
  in a sandbox where success is a concrete, checkable event (a forbidden tool call, an
  exfiltrated canary string, a policy violation logged by the harness). Exact truth, seconds
  of feedback, zero data cost.
- **Arena**: generators mutate attack payloads (tool descriptions, web pages, documents,
  MCP responses); discriminators mutate system prompts, tool-output filters, and permission
  policies. Fitness for attackers is breaches; fitness for defenders is breaches prevented
  minus false refusals on a held-out benign task set (the second term is what stops
  defenders from "winning" by refusing everything). Both populations are culled and cloned.
- **Why it is worth money**: 14 MCP CVEs and 200,000 exposed servers in one quarter, no
  vetting baseline, and IDEAS4 #9 (MCP security audit) needs exactly this engine. The
  outputs sell three ways: a hardened prompt and filter pack per client agent, a red-team
  report with reproducible payloads, and the evolving attack corpus as a CI test suite.
- **Reuse**: AllAllowed's sandboxed kernel and incident taxonomy are the harness; the
  journal already records every tool call and its consequence.
- **Gameability**: low if the benign task set is sealed; attackers cannot forge a canary
  exfiltration and defenders pay for refusals.
- **First experiment**: 20 seed payloads, 5 seed defenses, 200 generations, plot breach rate
  against false refusals, publish the frontier.
- **Scores**: realism 4, ease 4, 300 to 3,000 EUR per month (reports and packs).

### 2. E-invoice fraud generator versus detector
- **Metric**: detection rate on synthetic fraudulent Factur-X and UBL invoices (duplicate
  with altered IBAN, ghost supplier, split invoices under approval thresholds, VAT rate
  games) at a fixed false-positive rate on a sealed set of real, legitimate invoices.
- **Arena**: generators produce fraud variants that must still validate against the
  EN 16931 schematron (an invalid invoice is not a fraud, it is a bug); detectors are rule
  sets and small models; co-evolution hardens the detector against the attacks it has not
  seen. The mandatory e-invoicing reform (reception for all since 1 September 2026,
  emission for SMEs from 1 September 2027) creates the structured data this needs.
- **Why it is worth money**: accountancy firms and PDP platforms need fraud screening on
  invoice flows they did not have a year ago; the detector sells as a module of the
  Factur-X toolkit (IDEAS4 #5) at 29 to 99 EUR per month per company or per 1,000 invoices.
- **Gameability**: the sealed set of legitimate invoices from a partner firm is the truth;
  without one, the arena trains on its own imagination.
- **First experiment**: 500 synthetic legitimate invoices, 12 fraud patterns, evolve until
  a naive rules detector is broken, then evolve the detector back.
- **Scores**: realism 3, ease 3, 200 to 2,500 EUR per month.

### 3. Bug generator versus test generator (mutation score arena)
- **Metric**: mutation score, the share of injected faults the test suite kills, on a
  sealed set of real historical bugs from the repository's own git history (a mutant that
  reproduces a fixed bug is a real label).
- **Arena**: one population writes semantically plausible faults, the other writes tests;
  a test gains fitness only for killing mutants that also compile and pass on the original
  code (no flaky wins). You already run mutation testing on the VIEWPOINT port.
- **Why it is worth money**: IDEAS #2 (test-suite retrofitting) priced at 300 to 800 EUR
  per module becomes a machine with a defensible number attached: "your suite killed 31%
  of realistic faults, now 84%".
- **Gameability**: tests that assert implementation details kill mutants but break on
  refactors; add a held-out set of behavior-preserving refactors that the suite must
  survive. Coding-adjacent, so it belongs with the part 1 ideas, listed here because the
  mechanic is the purest GAN in the set.
- **Scores**: realism 4, ease 4, 500 to 3,000 EUR per month.

---

## Family B: selection against an exact objective the world already computes

### 4. Operations research for SMEs (routes, shifts, timetables)
- **Metric**: kilometers driven, overtime hours, unmet demand, or rule violations on the
  client's real instances (last month's deliveries, next month's shift constraints, a
  school's rooms and teachers). The objective is arithmetic; the truth is exact and instant.
- **Arena**: FunSearch and AlphaEvolve style. Agents write and mutate heuristics or
  solver configurations; the engine evaluates each on the sealed instance set; the best are
  cloned with mutation. The population, not any single agent, is the product.
- **Why it is worth money**: a delivery firm with eight vans that drives 6% fewer
  kilometers saves fuel and hours every month; a care agency that cuts shift-planning from
  two days to one hour pays for it; both are sold as a monthly plan (200 to 800 EUR) with
  the saving measured against the client's own history. No LLM in production: the winner is
  plain code the client can read.
- **Reuse**: make_money's evolution loop and MAP-Elites prototype; Exchange's held-out bank
  for the instance split.
- **Gameability**: near zero when constraints are hard-coded in the evaluator; the risk is
  overfitting to last month's geography, which the walk-forward split catches.
- **First experiment**: take one public VRP benchmark and one real dataset from a friend's
  business, evolve for a night, report kilometers against their current plan.
- **Scores**: realism 4, ease 3, 500 to 4,000 EUR per month.

### 5. SQL and hot-path optimization arena
- **Metric**: wall-clock and cost of a query or function on the client's real workload,
  with result equality against the original as a hard constraint (a faster wrong answer
  scores zero).
- **Arena**: agents rewrite queries, add indexes, or restructure code; the engine runs
  each variant against a frozen database snapshot and a replayed query log; fitness is
  cost saved per month at the client's cloud prices.
- **Why it is worth money**: database and compute bills are line items with an owner;
  savings are invoiced as a share (20 to 30% of the first year) or a fixed sprint (1,500 to
  4,000 EUR). Cousin of LLMargin, with exact truth instead of eval parity.
- **Gameability**: equality checks and replayed logs make it hard to fake; the danger is
  optimizing a snapshot that does not match production, hence the walk-forward on a later
  log.
- **Scores**: realism 4, ease 3, 500 to 4,000 EUR per month.

### 6. Net-income optimizer on the official rules engine (OpenFisca)
- **Metric**: net disposable income or total contributions for a given household or
  micro-business profile, computed by OpenFisca, the open-source engine that encodes French
  tax and benefit law. Deterministic truth by construction.
- **Arena**: agents explore the space of legal choices (legal status, VAT regime options,
  timing of income, declared options, benefit claims) for a profile; the engine scores each
  configuration; selection finds the frontier. Explicitly bounded to choices the law offers;
  the evaluator refuses anything outside the declared option space.
- **Why it is worth money**: freelancers and small-business owners pay accountants for
  exactly this question, once a year, and the answer is a report: 49 to 149 EUR per
  optimization, or a monthly tool for accountants. Pairs with IDEAS2 #20.
- **Gameability**: the engine is the law as coded; the risk is the law as coded lagging the
  law, so every report carries the OpenFisca version and a "verify with your accountant"
  line. Never drift into concealment: the option space is the moat and the safety.
- **Scores**: realism 3, ease 3, 200 to 2,500 EUR per month.

### 7. Home and SME energy arbitrage against real tariffs
- **Metric**: euros on the bill, computed from a real meter series and the real tariff
  (Tempo and dynamic tariffs, day-ahead prices for larger sites); with a battery or
  flexible loads, realized savings against the do-nothing baseline.
- **Arena**: agents produce control policies (when to charge, heat, run machines); the
  engine replays them over historical meter data and prices; the best are cloned. Then the
  same policy runs live on a small site.
- **Why it is worth money**: the metric is the bill; a bakery or a workshop with a
  time-shiftable load pays a share of savings. Small per site (10 to 80 EUR per month),
  many sites.
- **Gameability**: none on historical replay; the live risk is comfort and equipment
  constraints, which must be hard constraints in the evaluator.
- **Scores**: realism 3, ease 3, 100 to 1,500 EUR per month.

---

## Family C: selection where the platform runs the experiment for free

The cheapest truth in the world is an A/B test somebody else hosts. Three platforms run
controlled experiments natively and report the winner: Google Play store-listing
experiments, YouTube's thumbnail and title comparison, and any email tool's split test.
The arena generates variants, the platform provides the label, the journal records it.

### 8. Store-listing and creative evolution
- **Metric**: install conversion rate from store page views (Google Play listing
  experiments), thumbnail click-through with watch-time guard (YouTube), reply or booking
  rate (email sequences under CNIL B2B rules). Real users, days of feedback, free.
- **Arena**: agents mutate icons, screenshots, titles, descriptions, thumbnails, subject
  lines; each generation is one platform experiment; winners are cloned. Downstream guards
  (D1 retention for installs, watch time for clicks, meeting held for replies) are part of
  fitness so clickbait loses.
- **Why it is worth money**: it is the distribution problem that MOBILE_GAMES_BUSINESS_PLAN.md
  identified as the whole risk, and it sells to app developers and creators at 49 to 199
  EUR per month or as a managed service.
- **Gameability**: high without the downstream guard; with it, moderate. Platform rules
  forbid misleading assets; the evaluator must reject anything not in the product.
- **Scores**: realism 3, ease 4, 300 to 2,500 EUR per month.

### 9. Demand forecasting for perishable retail (waste and stockouts)
- **Metric**: euros of waste plus euros of lost sales, computed from the shop's real daily
  sales after the fact. Truth is the till.
- **Arena**: forecasting agents (statistical, LLM-prompted with weather and calendar, hybrid)
  propose tomorrow's production or order quantities; the engine scores each against realized
  sales; coop weighting learns whom to trust per product and weekday. Feedback daily.
- **Why it is worth money**: a bakery throwing away 8% of production and a florist
  discounting on Mondays both see the number on their own reports; 60 to 200 EUR per month
  per shop against a measured reduction. The pmx coop machinery (Brier against the market)
  becomes waste against the baseline order.
- **Gameability**: none, the till is the truth; the risk is the shop not following the
  suggestion, so measure adherence too.
- **Scores**: realism 3, ease 3, 300 to 2,500 EUR per month.

---

## Family D: coop ensembles where diversity is the edge

### 10. Learning-gain arena for exercise generation
- **Metric**: measured learning gain (post-test minus pre-test on a sealed item bank)
  for students who practiced with a given generated exercise set, versus a control set.
  The truth is a graded test the students actually took.
- **Arena**: agents generate exercise sets for one competence block; each week a class or
  cohort is randomly assigned sets; the engine computes gains; poor generators are culled.
  Coop weighting learns which generator works for which learner profile.
- **Why it is worth money**: training providers are paid on completion and success; a
  measured gain is a sales argument and a cost saver. Your edtech context is the access.
  Slow feedback (weeks), so it needs many parallel cohorts, which a large provider has.
- **Gameability**: teaching to the sealed test is the classic failure; rotate item banks
  and keep them sealed. Ethics review and consent are not optional.
- **Scores**: realism 2, ease 2, 0 to 2,000 EUR per month (mostly through an employer or
  partner, not as a solo product).

### 11. Support-answer arena scored on no-reopen
- **Metric**: tickets resolved with no reopen within 7 days and no refund escalation,
  from the client's helpdesk data. Truth is the customer's later silence, which is real if
  delayed.
- **Arena**: several answer-drafting agents (different knowledge cuts, tones, policies)
  propose replies to the same tickets; a human sends one; the engine attributes the outcome;
  coop weighting learns which agent to trust per ticket class. ideas3 #6 (support knowledge
  management) gets its scoring engine.
- **Why it is worth money**: staff minutes per resolved case and repeat-contact rate are
  numbers support managers already report.
- **Gameability**: closing tickets is gameable, silence after closure much less so; still
  exclude "customer gave up" by requiring a satisfaction ping on a sample.
- **Scores**: realism 3, ease 3, 300 to 2,000 EUR per month.

### 12. Synthetic training data scored by downstream accuracy
- **Metric**: accuracy of a small downstream model trained on generated data, evaluated on
  a sealed set of real labeled data the client owns. Exact and fast.
- **Arena**: generators produce datasets under privacy constraints; the discriminator is
  not a model but the downstream benchmark; selection keeps generators whose data trains
  the best model. Sells data, not models, to teams that cannot share real records
  (health, HR, finance).
- **Gameability**: leakage of the sealed set into generation is the whole risk; the
  held-out bank's refuse-on-reuse logging is the control.
- **Scores**: realism 2, ease 3, 200 to 2,500 EUR per month.

---

## Ideas considered and dropped

| Idea | Why not |
|---|---|
| Recruiting rank optimized on hires retained 6 months | Feedback in months, few labels, bias and legal exposure dominate any edge |
| Negotiation agents against real suppliers | Metric is money saved but the counterparty is a human who did not consent to be an arena |
| Dynamic consumer pricing evolved on real buyers | Real revenue truth, but price discrimination law and reputational risk; only acceptable on your own stock with a floor and a ceiling |
| Grant and tender writing scored on awards | One label per quarter; no selection converges on that |
| Ad-spend allocation across channels | Real ROAS, but the platforms' own bidders already do this better with more data |

---

## Ranking

Sorted by realism plus ease, ties by upper revenue bound. Truth, speed and gameability are
the arena axes; the last column is how much of the GAN code is reused as is.

| # | Arena | Mechanic | Truth | Feedback | Gameability | Realism | Ease | Score | EUR/month | Reuse |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 Prompt-injection red vs blue | Co-evolution | Exact | Seconds | Low | 4 | 4 | 8 | 300-3,000 | AllAllowed sandbox, journal, incident taxonomy |
| 2 | 3 Bug vs test generators | Co-evolution | Exact | Minutes | Medium | 4 | 4 | 8 | 500-3,000 | Evolution loop, held-out bank |
| 3 | 4 Operations research for SMEs | Selection | Exact | Instant | Very low | 4 | 3 | 7 | 500-4,000 | make_money MAP-Elites, held-out bank |
| 4 | 5 SQL and hot-path optimization | Selection | Exact | Minutes | Low | 4 | 3 | 7 | 500-4,000 | Evolution loop, journal |
| 5 | 8 Store-listing and creative evolution | Selection | Real users | Days | Medium | 3 | 4 | 7 | 300-2,500 | Journal, selection loop |
| 6 | 2 E-invoice fraud gen vs detector | Co-evolution | Exact on sealed set | Seconds | Low | 3 | 3 | 6 | 200-2,500 | AllAllowed forger archetype, held-out bank |
| 7 | 6 OpenFisca net-income optimizer | Selection | Exact (as coded) | Instant | Low | 3 | 3 | 6 | 200-2,500 | Evolution loop |
| 8 | 9 Perishable demand forecasting | Coop | Exact | Daily | None | 3 | 3 | 6 | 300-2,500 | pmx scoring and walk-forward |
| 9 | 11 Support answers on no-reopen | Coop | Delayed real | Weeks | Medium | 3 | 3 | 6 | 300-2,000 | pmx coop weighting |
| 10 | 7 Energy arbitrage on real tariffs | Selection | Exact | Daily | None | 3 | 3 | 6 | 100-1,500 | Evolution loop |
| 11 | 12 Synthetic data by downstream accuracy | Selection | Exact | Minutes | Leakage risk | 2 | 3 | 5 | 200-2,500 | Held-out bank |
| 12 | 10 Learning-gain exercise arena | Coop | Real, slow | Weeks | High | 2 | 2 | 4 | 0-2,000 | pmx coop weighting |

## Top 3 and how they connect to the rest of the folder

1. **Prompt-injection red versus blue (#1).** The only literal GAN in the set with exact,
   instant, free truth, and it is the engine behind IDEAS4 #9, the MCP security audit. The
   attack corpus it breeds is a product on its own (a CI suite), and the public frontier
   plot is the marketing.
2. **Operations research for SMEs (#4).** Exact objective, zero gameability, and the
   winner is readable code the client keeps. It is the make_money evolution loop pointed at
   a real cost line instead of simulated money, and it sells to the same local businesses
   as IDEAS2.
3. **Bug versus test generators (#3).** Turns IDEAS #2 from a service into a measured
   machine and reuses mutation testing you already run. Coding-adjacent, so it competes
   with part 1 for the same buyers, but the mechanic is the cleanest demonstration that
   co-evolution produces value.

The pattern across all twelve: the arena is never the product. The product is the winner
it breeds (a filter pack, a routing heuristic, a test suite, a store listing, an order
quantity) plus the number that proves it, logged before the outcome and never edited after.
That is the Exchange rule, and it is also the sales pitch.
