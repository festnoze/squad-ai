# Ventures

Two ideas selected from ../IDEAS.md for the best effort-to-cash ratio, refined
into concrete offers with implementation-ready PRDs. Each PRD is written as a
build contract: an agent fleet can implement it without further product
decisions.

## Tier 1: easy money (fast access, modest ceiling)

| Venture | Type | First euro | Recurring | Automation |
|---|---|---|---|---|
| [RepoAtlas](repoatlas/PRD.md) | Productized service (fixed-price doc packs); now the wedge of the [RepoAtlas Platform](repoatlas/PLATFORM.md) ladder (Score, Pack, Capture, Shield, Forge, Evolve, Tower) reaching requirement-driven evolution of legacy systems | ~2 weeks (first client) | Tower 690-2,490 EUR/month; Evolve capacity retainers 8-20k EUR/month | ~85% (pipeline delivers, human reviews) |
| [Shiplog](shiplog/PRD.md) | Micro-SaaS (changelog generator + hosted pages) | ~4-6 weeks (first subscriber) | 19 EUR/month per project | ~95% after setup |

Strategy: RepoAtlas brings cash first (no product build, only a delivery
pipeline plus a landing page). Shiplog compounds slowly in the background.
The RepoAtlas pipeline and the Shiplog generator share the same skill set:
headless Claude pipelines with strict verification gates.

## Tier 2: ambitious (hard access, 10-50x deal sizes)

| Venture | Type | Deal size | The barrier | The unlock |
|---|---|---|---|---|
| [ActProof](actproof/PRD.md) | EU AI Act compliance engine | 4,900 EUR packs, 690-1,990 EUR/month retainers, white-label rev share | Compliance buyers do not trust solo devs | Sell THROUGH DPO consultancies and law firms who white-label the engine |
| [LLMargin](llmargin/PRD.md) | LLM spend optimization, paid as % of verified savings | 10-60k EUR per engagement | Needs clients with >= 20k EUR/month LLM spend and pipeline trust | Metadata-only free audit collapses the trust barrier; Dspy-er is the engine |

Both tier-2 ventures reuse the tier-1 pipeline patterns (claude_client.py,
path/claim verification gates) and existing assets (Dspy-er, Langfuse
experience). Sequence: tier 1 funds the runway; tier 2 is where the money is.

Domain names listed in each PRD are candidates only: check availability on a
registrar before printing them anywhere.

The RepoAtlas B2B marketing site lives in [repoatlas/website/](repoatlas/website/)
(static, zero build: open index.html or serve with `python -m http.server 8096`).
