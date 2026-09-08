# Business plan: mobile games monetized with ads and in-app purchases

Research date: 6 September 2026. Currency EUR unless marked USD (1 USD = 0.92 EUR).
All tables come from [mobile_games_model.py](mobile_games_model.py); change an
assumption there, rerun, and paste. Companion to the idea lists in this folder and to
[IDEAS_RANKING.md](IDEAS_RANKING.md), whose realism, ease and revenue scales are reused.

## 1. Executive summary

**Verdict: as a business, ad- and IAP-monetized mobile games are a lottery ticket with a
cheap entry price for this profile, not a plan for revenue in six months.** The median
outcome of a solo release with no marketing is under 50 EUR a month. The organic ceiling
(a well-optimized game with no paid acquisition) is around 4,000 to 5,000 EUR a month and
is reached by a few percent of releases. Buying installs is not viable for a solo
developer at 2026 prices: the lifetime value of a casual install (0.30 to 0.55 USD) is
below the cost of acquiring one everywhere except Android Europe, and only barely there.

What makes the ticket cheap is the toolchain already in this repo: Unity 6.3, a shipped
and verified puzzle port, agent fleets that build a game against a written contract in
days, and a test harness. If a store-ready hybrid-casual game costs 250 hours instead of
1,000, the portfolio math changes: four prototypes a year, three killed at soft launch on
retention numbers, one pushed to store. Even then the expected economic result of the
first year is negative or near zero once labor is valued at 30 EUR per hour, and positive
only in cash.

The recommendation (section 9) is therefore conditional: run games as a **portfolio side
bet with hard kill criteria**, monetize hybrid (rewarded video plus a remove-ads pack plus
cosmetics), use French and Canadian soft launches to read D1 and D7 before spending
anything, and treat a hybrid-casual publisher, not paid ads, as the only path to scale.
Fund it with one of the "Do now" services from IDEAS_RANKING.md, not the other way round.

## 2. The market in September 2026

- **Size and split.** Global mobile gaming IAP revenue fell 2% to 40 billion USD in the
  first half of 2026 while publishers' ad spend rose 8% to 7 billion USD. IAP is still
  about 65% of total mobile gaming revenue, but growth has plateaued (1.3% in 2025).
  Mature markets (US, Canada, Japan, Korea) derive up to 90% of revenue from IAP; ad
  revenue is 55 to 70% of earnings in India, Indonesia and Brazil.
- **Segments.** Hybrid casual is the only segment with meaningful IAP growth (+20% year
  on year). Hypercasual led downloads (22 billion installs in 2025), recovered thanks to
  rising CPMs, and is shifting to hybrid monetization (IAP layered on ads).
- **Ad prices (eCPM, USD per 1,000 impressions).** Tier 1 markets: rewarded video 15 to
  30, interstitial 5 to 8 (US up to 9.5 iOS and 11 Android), banner 0.5 to 1.5. Western
  Europe outside UK and Germany earns markedly less on rewarded video. eCPMs grew 2.5 to
  14% year on year across formats in the second quarter of 2026, iOS fastest.
- **Retention.** Industry averages 2026: D1 26%, D7 10%, D30 under 4%; three quarters of
  games sit below 3% at D28. Hybrid-casual publishers want D1 above 35%, D7 above 15 to
  20%, D30 above 6 to 8% before they sign a prototype.
- **Monetization benchmarks.** ARPDAU above 0.15 USD for ad-driven games and above 0.30
  USD for IAP-heavy games is considered healthy; hybrid games often exceed 0.25 USD.
  Those figures describe well-run, US-heavy titles, not an organic French indie audience.
- **Acquisition cost (CPI).** Global blended gaming CPI 0.56 USD, up 30% in a year.
  Casual games: 1 to 4 USD; puzzle about 3 USD iOS and 2 USD Android; US casual around
  1.7 USD; Europe 0.53 USD average, DACH 1.70; casual iOS 1.41 versus Android 0.14 in one
  dataset.
- **Organic reality.** A well-optimized game with zero paid marketing rarely exceeds 200 to
  500 organic installs a day (6,000 to 15,000 a month). Of 100 indie mobile releases, one
  reaches 10,000 USD a month in revenue and one in 300 reaches 30,000 USD.
- **Store fees.** Apple Small Business Program and Google Play both take 15% up to 1
  million USD a year (Apple 99 USD a year, Google 25 USD once). In the EU from 1 October
  2026, Apple charges 15% for small-business developers using its IAP, 10% with
  alternative payment processing or link-out, and 5% on transactions in apps distributed
  outside the App Store. Ad revenue is not subject to store commission.

## 3. Monetization models

| Model | How it earns | Typical yield | Fits a solo dev because | Fails when |
|---|---|---|---|---|
| Rewarded video | Player opts in to a 15 to 30 s ad for a reward (extra life, double coins, hint) | Highest eCPM, 10 to 30 USD tier 1; 1 to 3 impressions per DAU are realistic | Players like it, no churn penalty, works from day one | The game has nothing worth watching an ad for |
| Interstitials | Full-screen ad between levels or sessions | 5 to 8 USD tier 1; 2 to 4 per DAU before churn rises | Trivial to implement | Frequency kills D1; users buy remove-ads then vanish |
| Banners | Persistent bottom ad | 0.5 to 1.5 USD; 15 to 25 impressions per DAU | Passive filler | Almost worthless outside tier 1; hurts UI |
| Remove ads (IAP, one-time) | 2.99 to 4.99 USD | 0.5 to 1.5% of installs convert | The easiest IAP to ship; also the best signal of a game people like | It removes your best payers from the ad pool (modeled) |
| Cosmetics and powerups (IAP) | Skins, themes, boosters, hint packs | 1 to 3% payers, 8 to 16 USD lifetime per payer in casual | Zero balance risk for cosmetics; agents generate variants cheaply | Needs a progression system players care about |
| Starter and battle pass | Time-limited bundles unlocked around D3 to D7 | Lifts IAP ARPDAU 15 to 40% in freemium benchmarks | Adds the recurring layer without subscriptions | Requires live-ops cadence a solo dev rarely sustains |
| Subscription | Weekly or monthly VIP (no ads, daily bonus) | Small share of casual revenue | 15% fee after year one on Apple | Refund and churn management |
| Premium (paid app) | 2.99 to 6.99 USD upfront | Installs collapse by 20 to 50x versus free | Good fit for a puzzle game with a story (your VIEWPOINT port) | No discoverability without press or a feature |

Policy constraints that shape the design:
- **Privacy**: Apple ATT (tracking prompt) and GDPR consent (UMP or equivalent) are
  mandatory; consent rates and iOS attribution limits depress eCPM for non-consenting users.
- **Children**: a game that looks child-friendly falls under Families policies (Google)
  and Kids Category rules (Apple), which restrict ad networks and personalized ads. Aim at
  a clearly adult-casual audience or accept lower eCPM.
- **Ad SDKs**: LevelPlay (ironSource) or AdMob mediation with two or three networks is
  the standard; the Unity toolchain in this repo already has the LevelPlay and IAP skills.

## 4. Unit economics model

Definitions, all per install:
- **Player-days** = 1 + sum of retention over 180 days (piecewise power law through D1,
  D7, D30).
- **Ad LTV** = ad ARPDAU x player-days x (1 - share of installs that bought remove-ads).
- **IAP LTV** = (remove-ads conversion x price + payer conversion x lifetime ARPPU) x 0.85
  after the 15% store fee.
- **Monthly revenue at steady state** = installs per month x LTV (cohorts overlap once the
  game is older than its retention tail).
- **Break-even installs** = 12-month costs (cash plus imputed labor at 30 EUR per hour,
  the same convention as ideas3.md) divided by 12-month revenue per monthly install.

Retention assumptions:

| Curve | D1 | D7 | D30 | Player-days |
|---|---|---|---|---|
| weak (below industry average) | 20% | 6% | 2% | 3.8 |
| industry average 2026 | 26% | 10% | 4% | 6.4 |
| hybrid-casual publisher bar | 35% | 15% | 6% | 9.0 |

Ad load and blended eCPM (a French indie's organic audience is perhaps 30 to 40% tier 1,
so blends are far below the US headline numbers):

| Mix | Rewarded/DAU x eCPM | Interstitial/DAU x eCPM | Banner/DAU x eCPM | ARPDAU USD |
|---|---|---|---|---|
| low: mixed geos, light ad load | 1 x 6 | 2 x 3 | 15 x 0.3 | 0.017 |
| mid: 40% tier 1, hybrid-casual ad load | 2 x 10 | 3 x 5 | 20 x 0.5 | 0.045 |
| high: US-heavy, aggressive ad load | 3 x 18 | 4 x 8 | 25 x 1 | 0.111 |

IAP assumptions: "low" is a remove-ads pack at 2.99 USD with 0.5% conversion; "mid" adds
cosmetics with 1.5% payers at 9 USD lifetime; "high" is 1.5% remove-ads at 3.99 plus 3%
payers at 16 USD (skins plus a starter or battle pass).

Net LTV per install (USD):

| Retention | Ads only (mid) | Ads mid + IAP low | Ads mid + IAP mid | Ads high + IAP high |
|---|---|---|---|---|
| weak | 0.17 (ads 0.17 / iap 0.00) | 0.18 (ads 0.17 / iap 0.01) | 0.31 (ads 0.17 / iap 0.14) | 0.87 (ads 0.41 / iap 0.46) |
| industry average | 0.29 (ads 0.29 / iap 0.00) | 0.30 (ads 0.29 / iap 0.01) | 0.43 (ads 0.29 / iap 0.14) | 1.16 (ads 0.70 / iap 0.46) |
| publisher bar | 0.41 (ads 0.41 / iap 0.00) | 0.42 (ads 0.40 / iap 0.01) | 0.54 (ads 0.40 / iap 0.14) | 1.45 (ads 0.99 / iap 0.46) |

Three readings:
- Remove-ads alone adds almost nothing (0.01 USD per install). It is worth shipping as a
  signal and a courtesy, not as revenue.
- Cosmetics and passes are what move IAP: the difference between "IAP low" and "IAP high"
  is 0.45 USD per install, more than the entire ad LTV of an average game.
- Retention is worth as much as monetization: going from weak to publisher-bar retention
  multiplies ad LTV by 2.4 with identical ad load.

## 5. Scenarios per game

| Scenario | Installs/month | LTV USD | Revenue EUR/month | Revenue EUR/year | What it is |
|---|---|---|---|---|---|
| A. Typical release, no marketing | 500 | 0.07 | 34 | 412 | The median of the 100 indie releases |
| B. Decent ASO, small community | 3,000 | 0.43 | 1,175 | 14,104 | Store optimization, a devlog, one post that worked |
| C. Well-optimized organic ceiling | 12,000 | 0.43 | 4,701 | 56,417 | The top few percent; 200 to 500 installs a day |
| D. Featured or viral month | 60,000 | 0.54 | 29,966 | 359,591 | A store feature or a creator video; rarely repeats, so read it as one month, not a year |
| E. The 1-in-100 hit with a publisher | 300,000 | 1.45 | 399,419 | 4,793,032 | Gross; the publisher buys the installs and keeps 50 to 70%, so the developer's share is 120,000 to 200,000 EUR/month |

Scenario A uses weak retention and low monetization on purpose: a release nobody markets
also gets the worst geo mix and the least engaged players. Scenarios B and C are the same
game with more distribution; the difference between them is entirely store visibility.

## 6. Costs and time

| Item | Assumption | Basis |
|---|---|---|
| Build to store-ready | 250 hours | Agent-built hybrid-casual game with meta, ads, IAP, analytics, store assets, QA on real devices; the VIEWPOINT port took a similar order of magnitude including verification |
| Live operation | 10 hours a month | Bug fixes, store replies, ad mediation tuning, one content drop a quarter |
| Prototype for a soft-launch test | 80 hours | Core loop, 20 levels, analytics, no meta, no store polish |
| Cash, fixed | 350 EUR per game | Apple 99 USD/year, Google 25 USD, icon and store art, sound effects, LLM usage during the build |
| Cash, monthly | 60 EUR | LLM usage, capture and analytics tools; ad SDKs and Unity Personal are free below revenue thresholds |
| Labor value | 30 EUR/hour | Imputed, same convention as ideas3.md; not a wage |
| Not included | VAT, income tax, social charges, a company structure, paid acquisition | Add them before believing any cash figure |

## 7. Profit and loss per game, 12 months

| Scenario | Revenue EUR | Cash costs EUR | Cash result EUR | Imputed labor EUR | Economic result EUR | Hours |
|---|---|---|---|---|---|---|
| A. Typical release | 326 | 1,070 | -744 | 11,100 | -11,844 | 370 |
| B. Decent ASO | 11,166 | 1,070 | 10,096 | 11,100 | -1,004 | 370 |
| C. Organic ceiling | 44,663 | 1,070 | 43,593 | 11,100 | 32,493 | 370 |
| D. Featured month | 284,676 | 1,070 | 283,606 | 11,100 | 272,506 | 370 |
| E. Publisher hit (gross) | 3,794,483 | 1,070 | 3,793,413 | 11,100 | 3,782,313 | 370 |

Revenue counts 9.5 steady months out of 12 to allow cohorts to build up. Scenario B, a
perfectly respectable outcome, pays back cash handsomely and does not pay for the time.
Scenario C is where the year is clearly worth it. Scenarios D and E are not plans.

Installs per month needed to break even over 12 months, cash plus labor:

| Retention | Ads only (mid) | Ads mid + IAP mid | Ads high + IAP high |
|---|---|---|---|
| weak | 8,200 | 4,517 | 1,598 |
| industry average | 4,825 | 3,270 | 1,200 |
| publisher bar | 3,423 | 2,565 | 962 |

An average game with hybrid monetization needs about 3,300 organic installs a month to
justify the year at 30 EUR per hour. That is scenario B territory, achievable but not
typical.

## 8. Paid acquisition: why not, and when

Payback needs LTV at least 1.3 times CPI to absorb attribution loss and payment timing.

| Retention x monetization | LTV USD | Android EU casual (0.53) | Android US casual (1.50) | iOS EU casual (1.70) | iOS US puzzle (3.00) |
|---|---|---|---|---|---|
| average / ads mid / iap mid | 0.43 | no (0.80x) | no (0.28x) | no (0.25x) | no (0.14x) |
| good / ads mid / iap mid | 0.54 | no (1.02x) | no (0.36x) | no (0.32x) | no (0.18x) |
| good / ads high / iap high | 1.45 | OK | no (0.96x) | no (0.85x) | no (0.48x) |

Only a game with publisher-bar retention and aggressive, US-heavy monetization pays back
its installs, and only on Android Europe, the cheapest and lowest-yielding inventory. That
is the whole reason hybrid-casual publishers exist: they run UA at a scale and with
creative-testing tooling a solo developer cannot match, and they pay for it with 50 to
70% of net revenue. For this profile the rule is simple: never buy installs with your own
money; if the soft-launch numbers clear the publisher bar, pitch publishers.

## 9. Strategy

**Positioning.** Hybrid-casual puzzle or skill games for adults, portrait, one-thumb, 30
to 90 second sessions, with a light meta (collections, themes, daily goals) that gives
rewarded video something to reward and cosmetics something to sell. This is the segment
with IAP growth, the one where 250-hour builds are credible, and the one where your
existing puzzle work (perspective and scale mechanics from VIEWPOINT, voxel building from
CUBEFORGE) becomes a differentiated hook rather than another match-3.

**Monetization stack, in order of implementation.**
1. Rewarded video at two natural moments (continue after fail, double the reward), capped
   at three a day.
2. Remove-ads pack at 2.99 EUR, shown after the third interstitial, never before.
3. Interstitials every second or third level, never in the first session.
4. Cosmetics (themes, trails, block skins) at 0.99 to 4.99, generated in batches by
   agents; a starter pack at D3.
5. Banners only if the UI has dead space; otherwise skip them.

**Portfolio process, 12 months.**

| Phase | Weeks | Output | Gate to continue |
|---|---|---|---|
| Prototype 1 to 4 | 1 to 16 | Four 80-hour prototypes, each soft-launched on Android in France and Canada, 300 to 500 installs bought or earned per prototype via the cheapest possible test (a 50 EUR test campaign or a community post) | D1 >= 30%, D7 >= 10%, session length >= 5 min; kill anything below |
| Build the survivor | 17 to 28 | Store-ready game, full monetization stack, analytics, ASO pack in 6 languages | Ad ARPDAU >= 0.04 USD and remove-ads conversion >= 0.8% in soft launch |
| Launch and optimize | 29 to 40 | Worldwide release, weekly mediation and ad-load tuning, first cosmetics drop | 3,000 organic installs a month by week 40 (scenario B) |
| Scale decision | 41 to 52 | Either publisher pitch (if D1 >= 35% and D7 >= 15%) or maintenance mode at 5 hours a month | Publisher term sheet, or a second title reusing the same engine |

Portfolio economics from the model (4 prototypes, 3 killed, 1 survivor):

| Survivor reaches | Cash result year 1 | Economic result year 1 | Hours in the year |
|---|---|---|---|
| Scenario B | 9,856 EUR | -8,444 EUR | 610 (12.7 h/week) |
| Scenario C | 43,353 EUR | 25,053 EUR | 610 (12.7 h/week) |

The whole year fits the 10 to 15 hours a week budget, but it consumes all of it. That is
the real cost: a year of games is a year without the services that IDEAS_RANKING.md rates
as more likely to pay.

**Distribution that costs time, not money.** Store optimization in six languages, a
devlog on the agent-built process (which is itself a story that gets shared), short
gameplay clips, a Reddit and Discord presence in the genre, and submissions to Google Play
Indie programs and Apple's featuring form. Each is worth doing once per game; none is
worth more than four hours a week.

**What not to do.** No paid UA with own money (section 8). No hypercasual clone (the
publishers own that lane and its CPI). No children's aesthetic (ad restrictions). No
premium price on a first title (no discoverability). No live-ops promises you cannot keep
at 10 hours a month.

## 10. KPIs and kill criteria

| Metric | Kill | Continue | Publisher-grade |
|---|---|---|---|
| D1 retention | < 25% | 30 to 35% | > 35% |
| D7 retention | < 8% | 10 to 15% | > 15% |
| D30 retention | < 3% | 4 to 6% | > 6% |
| Ad ARPDAU (USD) | < 0.02 | 0.04 to 0.08 | > 0.10 |
| Remove-ads conversion | < 0.4% | 0.8 to 1.2% | > 1.5% |
| Payer conversion (cosmetics) | < 0.5% | 1 to 2% | > 3% |
| Organic installs/month at month 3 | < 1,000 | 3,000 | > 10,000 |
| Rewarded video opt-in rate | < 15% | 25 to 35% | > 40% |

Measure with the free Unity Analytics or Firebase plus the mediation dashboard; do not
buy an analytics subscription before scenario B.

## 11. Risks

- **Discoverability**: the dominant risk; the difference between scenario A and B is not
  the game, it is whether anyone sees it. Nothing in this plan removes it, only the
  portfolio approach spreads it.
- **Retention miss**: most prototypes will fail the D1 gate; that is the process working,
  but it means months with zero revenue.
- **Platform policy**: ad-frequency and privacy rules change yearly; a mediation SDK
  update can break a build; Apple and Google reviews can reject or delist.
- **eCPM volatility**: seasonal (Q4 up, Q1 down 20 to 30%) and geo-dependent; an audience
  that skews to low-tier geos halves the ad LTV in the model.
- **Time competition**: 610 hours is the entire yearly budget; a service client during the
  same year is not possible at this pace.
- **Publisher terms**: if a publisher signs, expect 50 to 70% of net revenue to go to
  them, exclusivity, and KPIs that can end the deal after the test.

## 12. Where it sits against the other ideas

On the IDEAS_RANKING.md scale: realism 2 (median outcome near zero, upper outcomes real
but rare), ease 4 (toolchain, skills and agent fleets already exist, no client to find),
score 6, "Later" bucket, tier XL by ceiling and tier S by median. It is the only row in
the whole set with a ceiling in the hundreds of thousands and a median below 50 EUR a
month. The sensible way to hold that ticket is the portfolio process above, funded by a
service, with the prototypes doubling as public case studies for the agent-building
work that the service ideas sell.

## Sources

- https://tenjin.com/blog/ad-mon-gaming-2026/
- https://bidlogic.io/2026/07/31/q2-2026-ecpm-growth-interstitial-rewarded-video-and-banner-trends/
- https://revenueflex.com/blog/app-ad-revenue-benchmarks-2026/
- https://appfollow.io/blog/mobile-game-ads-formats-monetization
- https://gamegrowthadvisor.com/blog/2026-03-17-mobile-game-kpis-benchmarks-2026/
- https://gamegrowthadvisor.com/blog/2026-04-16-hybrid-casual-game-design-strategy-2026/
- https://segwise.ai/blog/mobile-gaming-app-user-retention-strategies
- https://www.tap-nation.io/blog/kpis-that-matter-metrics-to-track-in-hybrid-casual-games/
- https://gamegrowthadvisor.com/blog/2026-03-17-user-acquisition-cpi-benchmarks-2026/
- https://foxdata.com/en/blogs/2026-mobile-game-user-acquisition-cost-benchmarks-how-much-should-you-spend/
- https://business.mistplay.com/resources/user-acquisition-cost
- https://cas.ai/blog/the-mobile-game-publishing-reality-why-most-indies-fail-and-what-actually-works/
- https://appagent.com/blog/mobile-game-marketing/
- https://sensortower.com/blog/h1-2026-digital-gaming-market-index
- https://gamedevreports.substack.com/p/sensor-tower-state-of-gaming-2026
- https://www.deconstructoroffun.com/blog/2026/2/2/state-of-mobile-2026
- https://azurgames.com/blog/what-happened-to-hypercasual-market-growth-over-the-past-year-and-where-it-stands-now/
- https://www.apple.com/newsroom/2026/08/apple-announces-changes-for-apps-in-the-european-union/
- https://techcrunch.com/2026/08/18/apple-overhauls-its-eu-app-store-fees-loosens-rules-for-alternative-app-stores/
- https://www.groovyweb.co/blog/how-much-does-it-cost-app-store
