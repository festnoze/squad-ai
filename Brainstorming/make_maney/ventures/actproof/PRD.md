# PRD: ActProof - EU AI Act compliance engine, sold through the people companies already trust

Status: draft v1. Ambitious tier: long sales cycle, regulatory domain, but
deal sizes 10-50x the RepoAtlas/Shiplog ventures. This document is the build
contract; an agent fleet can implement the product, but the channel strategy
(section 4) is what makes or breaks it and requires human relationship work.

## 1. Product summary and why now

ActProof is a compliance workspace that turns EU AI Act obligations into
generated, evidence-backed documentation. It inventories a company's AI
systems from their actual repos and traces, classifies each system's risk
tier with a deterministic rules engine, and generates plus maintains the
required deliverables: Article 50 transparency measures, Annex IV-style
technical documentation, risk management files, logging and human-oversight
evidence. Agents do the reading and writing; a rules engine (not an LLM)
does the legal classification; partner lawyers review templates, never
individual outputs.

Why now (verified August 2026):
- Article 50 transparency obligations (disclose AI interaction, mark
  synthetic content, label deepfakes) apply since August 2, 2026.
- High-risk obligations were postponed by the Digital Omnibus agreement to
  December 2, 2027 (Annex III stand-alone systems) and August 2, 2028
  (Annex I embedded systems). Companies now have a DEFINED 16-month runway
  and enormous confusion about what applies when - both are exactly what
  compliance tooling monetizes.
- Mid-size companies cannot afford Big-4 AI audits (80k+) and are underserved
  between "read the regulation yourself" and "hire Deloitte".

This is NOT legal advice and the product must never present itself as such:
it produces technical documentation and evidence that the client's counsel
signs off on. That framing is also the channel strategy (section 4).

## 2. Naming and domains

- Working name: **ActProof**
- Domain candidates (verify availability, in this order):
  1. actproof.eu
  2. actproof.com
  3. annexiv.eu (memorable to the exact buyer persona)
  4. aiact-ready.eu
- The free classification wizard (section 5, module M1) gets a memorable
  path on the same domain (`/check`), not a separate brand.

## 3. Offer and pricing (three rungs, each feeds the next)

| Rung | What | Price |
|---|---|---|
| Free wizard | 10-minute AI Act risk classification + obligations checklist + deadline calendar, emailed as PDF | 0 (lead magnet) |
| Readiness Pack | Full inventory + classification report + gap analysis + Article 50 implementation plan + doc skeletons, fixed scope | 4,900 EUR (one-off) |
| Compliance retainer | Living documentation: connected to repos/CI/traces, docs regenerate on change, evidence vault stays current, quarterly review call | 690-1,990 EUR/month by system count |
| White-label | The engine, branded for a law firm or DPO consultancy, per-client licensing | 30% revenue share |

Realistic money: 10 retainer clients = 8-20k EUR MRR. One consultancy
white-label = 5-15 clients arriving at once. This is the "more money" thesis:
same pipeline skills as RepoAtlas, 10x the contract value, because the buyer
is spending compliance budget (fear money), not documentation budget
(nice-to-have money).

## 4. Target and channel (the hard part, stated honestly)

- End customer: EU B2B companies, 20-300 employees, shipping AI features in
  or near Annex III areas (HR/recruiting tools, education and exam scoring,
  credit and insurance scoring, medical triage) plus every company touched
  by Article 50 (any customer-facing chatbot or content generator).
- BUT the primary sales motion is NOT direct. It is through DPO
  consultancies, privacy law firms, and CISO-as-a-service shops: they
  already have the trust and the client list, and they currently do this
  work with Word templates. ActProof is their production tool.
  Direct sales exist only via the free wizard funnel.
- Concrete channel plan: identify 30 FR/EU privacy consultancies (they all
  publish GDPR content; scraping their blogs is an agent task), offer 3 of
  them a free pilot on one of their clients in exchange for a case study
  and a white-label LOI.

## 5. Product spec: five modules

M1 **Classification wizard** (free, public): a questionnaire (15-25
   questions, branching) mapping to a DETERMINISTIC rules engine encoding:
   prohibited practices (Art 5), Annex III high-risk categories and their
   filter conditions, Article 50 transparency triggers, GPAI provider vs
   deployer roles, and the post-Omnibus deadline calendar. Output: per-system
   tier, applicable obligations list with article references, deadline
   dates, and a confidence note. The rules live in versioned YAML
   (`rules/aiact-YYYY-MM.yaml`) with citations per rule; an LLM NEVER makes
   the classification call, it only helps the user answer questions
   ("what does 'biometric categorisation' mean for my product?").

M2 **Inventory**: agents scan connected repos (read-only) for AI usage:
   LLM SDK calls, model files, inference endpoints, prompts, third-party AI
   APIs; merges with a human-filled register. Output: system register with
   evidence links (file paths), the same anti-hallucination gates as
   RepoAtlas (every claim cites an existing path).

M3 **DocFactory**: per system and tier, generates the document set from
   lawyer-reviewed templates + facts extracted by agents from code, evals,
   and traces. v1 document set: Article 50 transparency implementation doc,
   AI system description (Annex IV sections 1-3 style), risk management
   file skeleton with identified risks, data governance summary, human
   oversight description, logging capability report. Each generated section
   carries footnoted evidence references; sections lacking evidence render
   as explicit TODO blocks assigned to the client, never as invented prose.

M4 **Evidence vault**: continuous collectors: CI test results, eval runs
   (Langfuse integration is the differentiator nobody else has), model/
   version change log from git tags, incident register, oversight sign-off
   records. Everything timestamped and exportable as an auditor-facing
   bundle (zip with manifest and hashes).

M5 **Watchtower**: on repo change (webhook) or monthly, agents diff the
   inventory, flag classification-relevant changes ("you added emotion
   detection to the HR module: this changes your tier"), and regenerate
   stale docs as drafts for review. Also watches the regulation itself:
   when the rules YAML is updated (Omnibus final text, guidance documents),
   every client gets an impact diff. This module is why the retainer exists.

## 6. Architecture

- FastAPI on port 8500, Postgres, server-rendered dashboard (same stack
  philosophy as Shiplog). Multi-tenant from day one (white-label requires
  it): every table keyed by `org_id`, per-org branding config.
- Agent layer: headless Claude pipelines reusing the RepoAtlas
  `claude_client.py` pattern (subprocess, retry, JSON extraction, full
  logging); model `claude-sonnet-5` for extraction, `claude-opus-5` or
  better for document drafting.
- Connectors: GitHub/GitLab read-only App, generic webhook, Langfuse API
  (eval and trace metadata only, never trace payloads), manual upload.
- Security posture (sales blocker if absent): EU-hosted (Scaleway/OVH),
  client code never persisted (scan in ephemeral workspace, keep only
  extracted facts + paths), audit log of every access, DPA template ready.
- Repo layout:

```
actproof/
  app/            FastAPI: routers/ (wizard, dashboard, connectors, exports)
  rules/          aiact-YYYY-MM.yaml + rules_engine.py (pure functions,
                  exhaustively unit-tested, one test per rule citing its article)
  pipelines/      inventory/, docfactory/, watchtower/ agent stages + prompts
  templates/docs/ lawyer-reviewed jinja templates, versioned, changelog
  evidence/       collectors + bundle exporter
  tests/
```

## 7. Agent prompts (verbatim contracts, abbreviated set)

### 7.1 AI usage scanner (M2)

```
You are inventorying AI usage in a codebase for a compliance register.
Files (paths and contents):
{contents}
Identify every place this code USES or PROVIDES an AI capability: LLM API
calls, local model inference, third-party AI services, prompt definitions,
training or fine-tuning code. Reply with ONLY a JSON array:
[{"capability": "<what it does, one line>",
  "kind": "llm_api|local_model|third_party_ai|training|prompt_asset",
  "provider_or_model": "<if identifiable>",
  "files": ["<path>", ...],
  "user_facing": true|false,
  "notes": "<uncertainty or context, one line>"}]
Every path must appear in the input. Report only what is in the code; do
not speculate about what the company might also be doing.
```

### 7.2 Wizard helper (M1, assist-only)

```
You help a non-lawyer answer a compliance questionnaire about their AI
system. Question: "{question}" (relates to {article_ref}).
Their product description: {description}
Explain in {language}, in under 120 words, what the question means for a
product like theirs, with one concrete example of a YES case and a NO case.
You NEVER answer the question for them and NEVER state a classification;
end with "Your call:" and restate the question. No legal advice wording
("you must", "you are compliant"); use "the regulation describes".
```

### 7.3 Doc section writer (M3)

```
You draft one section of technical compliance documentation from verified
facts. Section: {section_title} ({template_ref}). Facts (JSON, extracted
from the client's code, evals and traces; every fact has evidence paths):
{facts_json}
Template guidance from the reviewed template:
{template_guidance}
Write the section in {language}. Every factual sentence must be traceable
to an input fact; add the evidence reference in the form [E{n}]. Where the
template requires information absent from the facts, insert exactly:
<!-- TODO(client): {what is missing and who typically provides it} -->
Never write "compliant", "meets the requirements", or equivalents: describe
what exists; assessment belongs to counsel. Return ONLY the markdown.
```

### 7.4 Watchtower differ (M5)

```
You compare two AI-usage inventories of the same codebase for compliance-
relevant changes. Previous: {old_json}. Current: {new_json}.
Classification-relevant changes are: new AI capabilities, removed ones,
user-facing changes, new data categories processed, provider/model changes.
Reply ONLY with JSON:
{"relevant_changes": [{"change": "<one line>", "why_it_matters":
"<which questionnaire answer or rule it could affect>",
"evidence": ["<path>", ...]}], "requires_reclassification": true|false}
```

## 8. Quality gates and legal guardrails (non-negotiable)

G1 Rules engine is pure deterministic code; 100% branch-tested; every rule
   carries its article citation and the rules file version is printed on
   every output document.
G2 Same path/claim verification gates as RepoAtlas for all extracted facts.
G3 Generated docs contain zero compliance ASSESSMENTS (lint rule scanning
   for forbidden phrases: "compliant", "conforme", "meets Article", "you
   must"); they contain descriptions plus evidence plus TODOs.
G4 Template changes require a recorded lawyer review (reviewer, date, diff)
   before deployment; the review log is itself a sales asset.
G5 Every client-visible page and PDF carries the disclaimer: "Technical
   documentation support tool. Not legal advice. Review by qualified
   counsel required." in the client's language.

## 9. Milestones

- M0 (weeks 1-2): rules YAML v1 (post-Omnibus timeline) + wizard live on
  the domain as a free tool; unit tests citing articles; French + English.
- M1 (weeks 3-5): inventory pipeline + DocFactory producing the Article 50
  transparency doc end-to-end on one of your own projects (dogfood: the
  Autospec or website-builder codebase makes a realistic guinea pig).
- M2 (weeks 5-8): find the reviewing lawyer (revenue share or hourly),
  templates v1 reviewed; Readiness Pack deliverable assembled manually
  around the pipeline for the first pilot client.
- M3 (weeks 8-16): 3 consultancy pilots; convert one to white-label LOI;
  first 2 paying Readiness Packs; retainer productized (M4+M5) only after
  two packs sold - do not build the vault before someone pays.

## 10. Acceptance criteria

1. The wizard classifies the 12 canonical scenario fixtures (one per Annex
   III category plus GPAI, Art 50-only, minimal-risk, prohibited) exactly
   as the rules file dictates, and updating the YAML changes results with
   no code change.
2. Inventory + DocFactory run unattended on a 100k LOC repo in under 1 hour
   and every evidence path in the output exists (G2 test).
3. The forbidden-phrase linter (G3) blocks a doc containing "compliant"
   (test with a planted phrase).
4. An auditor bundle exports as a zip with manifest and SHA-256 hashes and
   re-validates on import.
5. Wizard-to-email funnel works: completion -> PDF in inbox -> tagged lead
   row in the DB.

## 11. Non-goals (v1)

- No legal advice, opinions, or conformity assessments; no notified-body
  interactions; no CE-marking workflows (Annex I products are out of scope
  until the 2028 wave gets closer).
- No GDPR module (adjacent, tempting, scope-killer); no ISO 42001 mapping
  in v1 (fast follow for the white-label tier, consultancies will ask).
- No US/UK frameworks.
- No autonomous doc publication: everything ships as drafts for review.

## 12. Risks

- Deadline slip already happened once (Omnibus) and deflated urgency ->
  Article 50 applies NOW; lead with transparency obligations and sell the
  high-risk runway as "16 months is exactly enough time to do this
  properly", which is true.
- A lawyer partner is a hard dependency -> start the search at M0, not M2;
  the free wizard's traffic data is the recruiting pitch to them.
- Big compliance platforms (OneTrust, Vanta) move down-market -> the moat
  is the code-level evidence pipeline (they do questionnaires, ActProof
  reads repos and eval traces); stay where they cannot cheaply follow.
- Solo-dev credibility gap with compliance buyers -> that is precisely why
  the channel is consultancies white-labeling the engine, not direct
  enterprise sales.
