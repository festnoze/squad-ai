# Cover-message style guide (FR + EN)

The writer agent MUST follow this guide for every draft. The goal: messages
that read like a senior consultant wrote them personally in 10 minutes —
because a recruiter can smell a template or an unedited LLM blast instantly.

## Non-negotiable rules

1. **Truth only.** Every claim must trace to `config/profile.yaml` or the CVs.
   No invented metrics, clients, or certifications. Ever.
2. **Length.** Email: 120-180 words body. Platform message: 80-130 words.
   LinkedIn DM: 60-100 words. Shorter is better.
3. **Specificity.** Open on THEIR mission (one concrete detail from the offer:
   their stack, their problem, their product) — never on "I am...".
   Then 2-3 matched achievements max, chosen from `experience_highlights`.
4. **Language** = mission language rule (FR for France, EN elsewhere).
   Match register: FR = vouvoiement, professional but direct. EN = plain,
   confident, no corporate fluff.
5. **One CTA**, low friction: a short call ("un échange de 20 minutes",
   "a quick 20-minute call this week").
6. **CV attached** when the channel allows; say so in one clause, not a
   paragraph. Variant: short CV by default; full CV only if they ask for
   detailed background or it's an ESN/broker.
7. **No AI-isms.** Banned: "I am thrilled", "je suis passionné par", "delve",
   "leverage synergies", "n'hésitez pas", generic praise of their company,
   any sentence that could be pasted into another application unchanged.
8. **Rates**: never volunteer the TJM in a first message unless the offer
   asks; if asked, use profile.yaml rates plainly.
9. **Availability**: if the offer requires an immediate start, be honest per
   profile.yaml engagement.availability.

## Structure (email)

- **Subject**: `[their role title] — profil senior IA en production` /
  `[their role title] — senior AI engineer, production LLM systems`.
  Max 70 chars. No "candidature spontanée" (weak) — for cold outreach use
  a value hook: `IA en production + AI Act — un profil hybride pour [Company]`.
- **Line 1**: their context (the hook). One sentence.
- **Lines 2-4**: why me, mapped to them. 2-3 bullets or a tight paragraph
  drawing from experience_highlights + one differentiator.
- **Line 5**: CTA + CV mention.
- **Signature**: name, title, phone, LinkedIn URL. Nothing else.

## Example skeleton — FR (platform message, mission RAG)

> Bonjour, votre mission [X] touche exactement mon quotidien des deux
> dernières années : j'ai conçu et mis en production les chatbots et le
> callbot IA du leader français du e-learning (RAG complet, agents
> LangGraph/ADK, évaluations LLM-as-a-judge avec Langfuse).
> Au-delà de l'IA, j'apporte 25 ans d'architecture logicielle — de quoi
> intégrer ces systèmes proprement dans votre SI, avec les tests et
> l'observabilité qui vont avec.
> Disponible pour un échange de 20 minutes cette semaine si le profil vous
> parle. CV joint.

## Example skeleton — EN (email, US startup)

> Subject: Senior AI engineer — production RAG/agents, EU-based, full remote
>
> Hi [Name], saw you're building [their product/feature] — I've spent the
> last two years shipping exactly that kind of system: the production
> chatbots and voice bot of France's largest e-learning provider (full RAG
> pipelines, LangGraph/ADK multi-agent workflows, LLM-as-a-judge evals with
> Langfuse).
> What I add on top: 25 years of software architecture, so the AI lands in
> your codebase as production software, tested and observable — not a POC.
> Open to a quick 20-minute call this week? Resume attached.
>
> Etienne Millerioux — Lead AI Engineer
> +33 6 68 42 23 88 · linkedin.com/in/etiennemillerioux34

## Follow-up messages (relances)

- Max 2 per application, ≥5 days apart (config/targets.yaml caps).
- 40-70 words. Reference the original message in half a sentence, add ONE
  new element (a relevant experience detail or packaged offer from
  profile.yaml), re-issue the same low-friction CTA.
- Tone: light, zero guilt-tripping. FR: "Je me permets de remonter ce
  message..." EN: "Floating this back up —".
