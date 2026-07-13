# Improvement V3 — Boucle d'Observation, Gouvernance du Backlog & Mémoire Logicielle

> Source de vision : [Plan_Complet_Software_Factory_Agentique.md](Plan_Complet_Software_Factory_Agentique.md) (§7–§14).
> Ce plan traduit la vision en features implémentables dans l'Autospec actuel, sans casser l'existant.
> Convention respectée : chaque feature est derrière un flag, comportement inchangé flag OFF.

## Statut d'implémentation (2026-07-13)

**✅ V3 ENTIÈREMENT IMPLÉMENTÉ** — les 8 features sont livrées et vertes.
Suites : backend **1143 tests** (baseline pré-V3 : 878 ; +265 tests V3), frontend **239 tests** (baseline : ~201), `npm run build` OK.

| Feature | Statut | Code principal | Tests |
|---|---|---|---|
| F1 Observations | ✅ | `models.py`, `pipeline._aextract_observations` | `test_observations.py` (16) |
| F2 Critic+Router | ✅ | `orchestrator/observations.py` | `test_observation_router.py` (43) |
| F3 Gouvernance PO | ✅ | `orchestrator/governance.py`, phase GOVERN | `test_governance.py` (28) |
| F4 Mémoire | ✅ | `orchestrator/knowledge.py`, `autospec-knowledge.json` | `test_knowledge.py` (37) |
| F5 Pattern Detector | ✅ | `orchestrator/pattern_detector.py` | `test_pattern_detector.py` (27) |
| F6 Policy Engine | ✅ | `orchestrator/policy.py` | `test_policy.py` (87) |
| F7 UI | ✅ | `ObservationsPanel/GovernancePanel/KnowledgePanel.tsx`, badge ⚖ | 38 tests Vitest |
| F8 Cartographer | ✅ | `orchestrator/cartographer.py` | `test_cartographer.py` (27) |

Flags (tous OFF par défaut, comportement historique inchangé) : `OBSERVATIONS`, `OBSERVATION_CRITIC`, `OBSERVATION_DEDUP_THRESHOLD`, `OBSERVATION_ROUTER_LLM`, `GOVERNANCE`, `GOVERNANCE_AUTO` (déprécié → policy), quotas `GOVERN_MAX_*`, `GOVERN_ROLE_TIER`, `KNOWLEDGE`, `KNOWLEDGE_INJECT_MAX`, `KNOWLEDGE_MAX_PER_SECTION`, `PATTERN_DETECTOR`, `PATTERN_MIN_SIGNALS`, `PATTERN_MAX_FINDINGS`, `AUTONOMY_LEVEL` (défaut 2 = comportement actuel) + `AUTONOMY_<DOMAINE>`, `CARTOGRAPHER`, `CARTOGRAPHER_LLM`, `CARTOGRAPHER_HOT_FILES`.
Activation type de la boucle complète : `OBSERVATIONS=1 GOVERNANCE=1 PATTERN_DETECTOR=1` (+ `AUTONOMY_LEVEL=5` pour l'autonomie totale, sinon approbation humaine via l'UI/endpoints).

Écarts notables au plan (documentés dans les rapports de lots) : rétrogradations d'autonomie F6 limitées aux domaines backlog/spec (préservation du comportement par défaut) ; dépassement de quota F3 = auto-defer en idée en suspens ; watermark F5 avance aussi sur échec LLM ; ADRs exclus de la compaction F4.

---

## 0. État des lieux (ce qui existe déjà — ne PAS réimplémenter)

| Concept de la vision | Statut dans Autospec | Localisation |
|---|---|---|
| Coding/QA/Critic/Judge agents | ✅ Implémenté | `agents/personas.py`, `orchestrator/pipeline.py` |
| Evaluators (E6 produit, S1 sécurité) | ✅ Implémenté | `_aevaluate_phase`, `_asecurity_phase` |
| Retro / lessons globales (E7, F1) | ✅ Implémenté | `_aretro_phase`, `autospec-lessons.json` |
| Recovery machine, escalade, classification | ✅ Implémenté (W1) | `orchestrator/recovery.py` |
| Arbitrage wrong-test, Amendment human-gated | ✅ Implémenté (W2/W5.1) | `orchestrator/arbitration.py`, `amendment.py` |
| Constitution, guards anti-triche | ✅ Implémenté (W3/W0.5) | `orchestrator/constitution.py`, `guards.py` |
| Feedback utilisateur → impact backlog | ✅ Implémenté (E2) | `_aimpact_analysis`, `state.feedback[]` |
| Backlog d'hypothèses (auto-spec) | ✅ Implémenté | `FeatureHypothesis`, BacklogPanel |
| Télémétrie / scorecard KPI | ✅ Implémenté (W0) | `orchestrator/scorecard.py`, `build_monitor.py` |
| Tier routing coût (worker/boss/checker) | ✅ Implémenté (W4) | `config.py` ROLE_ROUTING |

**Les manques que V3 comble** (vision §7–§14) :

1. ❌ Le Coding Agent ne produit **que** du code/tests : aucune **Engineering Observation** structurée (workaround, dette, risque, ambiguïté, contrainte découverte…).
2. ❌ Aucun **Observation Critic / Router** : les findings E6/S1 vont en vrac dans `state.feedback[]` (texte libre).
3. ❌ Le PO ne **gouverne pas le backlog** après implémentation : il ne peut ni créer de TS/US/Epic à partir des découvertes du dev, ni enrichir les AC, ni reporter une idée.
4. ❌ Pas de **mémoire logicielle multi-niveaux par projet** : pas d'ADR, pas de registre de dette, pas de registre de risques, pas d'« idées en suspens ». Seules existent les lessons globales cross-projet (coach E7) et la calibration.
5. ❌ Pas de **Pattern Detector** : aucune agrégation des signaux (observations, guard_findings, calibration) pour détecter un composant problématique.
6. ❌ Pas de **Policy Engine d'autonomie** : les gates sont binaires et épars (`AMENDMENT_AUTO`, `auto_spec`, approbation composants). Pas de niveaux 0–5, pas d'autonomie effective ajustée par les signaux.
7. ❌ Pas de visibilité UI sur observations / décisions PO / mémoire.

---

## 1. Vision fonctionnelle globale V3

Une tâche ne produit plus seulement un incrément logiciel. Elle produit **des preuves + des observations + de la connaissance + des mises à jour potentielles du backlog** (vision §19).

```
Dev/QA terminent un work item (DONE ou FAILED)
        ↓
[F1] Observation Extractor (worker tier) lit la transcription
        → 0..3 EngineeringObservation structurées
        ↓
[F2] Observation Critic : dédoublonne, valide les preuves, score
        ↓
[F2] Observation Router : route par type
        ├─→ po            → file d'attente gouvernance
        ├─→ architecture  → mémoire archi / proposition d'ADR
        ├─→ debt          → registre de dette
        ├─→ risk          → registre de risques
        ├─→ security      → findings sécurité (pipeline S1 existant)
        └─→ discovery     → idées en suspens (pending_ideas)
        ↓
[F5] Pattern Detector (ambient, fin d'itération) : agrège
        → méta-observations (refactoring global, composant fragile)
        ↓
[F3] PO Backlog Governor (phase GOVERN, fin d'itération) : décide
        create_task | create_story | create_epic | update_story |
        enrich_criteria | defer | persist | dismiss
        ↓
[F6] Policy Engine : allow / require_human / deny selon niveau d'autonomie
        ↓
Backlog mis à jour + [F4] mémoire mise à jour → prochaine itération
        (le PO et le Dev reçoivent la connaissance pertinente injectée)
```

Invariants (vision §2 et §9) :
- **Le Coding Agent observe, il ne décide pas de la roadmap.** L'extractor émet, le PO gouverne.
- **Aucun agent ne valide son propre travail** : l'Observation Critic est un rôle checker distinct de l'extractor.
- **Toute décision est traçable** : chaque décision PO est journalisée avec l'observation source et les preuves.
- **Toutes les observations ne deviennent pas des tâches** (vision §11) : `persist`/`defer`/`dismiss` sont des issues de première classe.

---

## 2. Features

### V3-F1 — Engineering Observations (socle)

**But** : après chaque work item, capturer les découvertes du Dev/QA sous forme structurée.

**Modèle** (`models.py`) :

```python
class ObservationType(str, Enum):
    WORKAROUND = "workaround"; TECH_DEBT = "tech_debt"; RISK = "risk"
    LIMITATION = "limitation"; REFACTORING = "refactoring"
    IMPROVEMENT = "improvement"; AMBIGUITY = "ambiguity"
    CONSTRAINT = "constraint"; PATTERN = "pattern"  # PATTERN réservé au detector F5

class ObservationStatus(str, Enum):
    NEW = "new"; VALIDATED = "validated"; REJECTED = "rejected"
    ROUTED = "routed"; ACTIONED = "actioned"; PERSISTED = "persisted"
    DEFERRED = "deferred"; DISMISSED = "dismissed"

class EngineeringObservation(BaseModel):
    id: str                      # "OBS-<n>"
    type: ObservationType
    summary: str                 # 1 ligne
    description: str = ""
    evidence: list[str] = []     # extraits de transcription, chemins de fichiers, sorties de tests
    impact: str = ""             # composant/story impactés + conséquence
    confidence: float = 0.5      # 0..1 (auto-évalué par l'extractor, révisé par le critic)
    urgency: str = "normal"      # "low" | "normal" | "high" | "critical"
    workaround: str = ""         # contournement appliqué, le cas échéant
    recommendations: list[str] = []
    reevaluate_when: str = ""    # condition de réévaluation (vision §8)
    source_role: str = ""        # "dev" | "qa" | "pattern-detector" | "evaluator" | "security"
    work_item_id: str = ""       # story/task d'origine
    stream: str = ""             # stream du work item
    iteration: int = 0
    status: ObservationStatus = ObservationStatus.NEW
    routed_to: str = ""          # "po"|"architecture"|"debt"|"risk"|"security"|"discovery"
    resolution: str = ""         # décision finale (renseignée par F3)
```

`ProjectState.observations: list[EngineeringObservation] = []` + compteur `observation_seq`.

**Extraction** : nouvelle fonction `prompts.observation_extract(state, item, transcript_tail)` — appel **worker tier** (pas de session lourde) après `_abuild_work_item` (DONE **et** FAILED : les échecs sont les plus riches en découvertes). Entrée : titre/AC du work item, queue de transcription dev+qa (via `interactions.py`, dernières interactions du work item), `last_error`, `guard_findings`. Sortie JSON : liste de 0..3 observations. Extraction **fail-open** : toute erreur → 0 observation, jamais de blocage du build.

**Sources supplémentaires** (raccordement, pas de nouveau code d'extraction) : les findings E6 (`_aevaluate_phase`) et S1 (`_asecurity_phase`) sont convertis en `EngineeringObservation` (`source_role="evaluator"/"security"`) au lieu d'être uniquement poussés en texte libre dans `state.feedback[]` (le fallback texte libre est conservé flag OFF).

**Config** : `OBSERVATIONS=0|1` (défaut 0), `OBSERVATIONS_MAX_PER_ITEM=3`, `OBSERVATIONS_ROLE_TIER=worker`.

**Découpage en stories** :
- **US-F1.1** Modèles + persistance : `EngineeringObservation` dans `models.py`, sérialisation dans `storage.py`, migration lecture d'anciens états sans le champ. *AC : un état legacy se charge sans erreur ; round-trip JSON complet.*
- **US-F1.2** Prompt + parsing : `observation_extract()` dans `prompts.py`, persona `observer` (fallback dans `personas.py`), parsing robuste via `extract_json`. *AC : sortie malformée → 0 observation, log warning, build non bloqué.*
- **US-F1.3** Hook pipeline : appel dans `_abuild_work_item` (fin, DONE/FAILED), sous flag ; événement bus `observation` publié ; interaction enregistrée dans le sidecar. *AC : flag OFF → zéro appel LLM supplémentaire ; flag ON → observations dans l'état + événement SSE.*
- **US-F1.4** Raccordement E6/S1 : conversion des findings en observations (`source_role` correct). *AC : un finding evaluator devient une observation typée `improvement`/`risk`.*

**Fichiers** : `models.py`, `storage.py`, `prompts.py`, `personas.py`, `config.py`, `pipeline.py` (hook ~20 lignes), `events.py` (type d'événement), tests `tests/test_observations.py`.

---

### V3-F2 — Observation Critic & Router

**But** : filtrer le bruit, dédoublonner, router (vision §9 et §14 : Observation → Critic → Router → agents spécialisés).

**Nouveau module** : `orchestrator/observations.py`.

**Critic** (2 étages, déterministe d'abord — philosophie Autospec) :
1. **Déterministe** : rejet si `summary` vide, `evidence` vide, ou doublon quasi-exact (similarité de tokens > seuil vs observations existantes non-dismissées du même stream). Fusion des doublons : la nouvelle preuve est ajoutée à l'observation existante, `confidence` est augmentée (signal répété = signal fort — alimente F5).
2. **LLM checker tier** (uniquement sur le lot restant, un seul appel batché par work item) : valide « preuve soutient l'affirmation », révise `confidence` et `urgency`. Rôle `observation-critic`, indépendant de l'extractor (vision §2 : personne ne valide son propre travail).

**Router** (déterministe par défaut, table type→destination) :

| type | destination |
|---|---|
| ambiguity, improvement, limitation | `po` |
| refactoring, constraint, pattern | `architecture` (+ copie `po` si `urgency>=high`) |
| tech_debt | `debt` |
| risk | `risk` |
| workaround | `debt` + `po` si `urgency>=high` |
| (source_role=security) | `security` |

Les destinations `debt`/`risk`/`architecture`/`discovery` écrivent dans la mémoire F4 ; la destination `po` alimente la file de gouvernance F3. Cas ambigus (confiance basse, multi-impact) : appel LLM router (checker tier) optionnel `OBSERVATION_ROUTER_LLM=0|1`.

**Config** : `OBSERVATION_CRITIC=1` (actif dès que `OBSERVATIONS=1`), `OBSERVATION_DEDUP_THRESHOLD=0.75`.

**Découpage** :
- **US-F2.1** Critic déterministe + fusion doublons (pur, testable sans LLM). *AC : doublon détecté → fusion + confidence accrue ; observation sans preuve → REJECTED.*
- **US-F2.2** Critic LLM batché + prompt `observation_critic()`. *AC : appel unique pour N observations ; échec LLM → observations passent en VALIDATED avec confidence inchangée (fail-open).*
- **US-F2.3** Router déterministe + branchement mémoire/gouvernance. *AC : chaque type atterrit dans la bonne destination ; statut ROUTED + `routed_to` renseigné.*

**Fichiers** : `orchestrator/observations.py` (nouveau), `prompts.py`, `personas.py`, `config.py`, `pipeline.py` (appel après extraction F1), tests `tests/test_observation_router.py`.

---

### V3-F3 — PO Backlog Governor (phase GOVERN)

**But** : le cœur de la demande — le PO reçoit le retour d'implémentation et **met à jour la connaissance, les idées en suspens, et les specs** : modifier des US existantes, enrichir des AC, créer tâches/US/TS/Epics (vision §10).

**Nouvelle phase** `GOVERN` dans `PipelinePhase`, exécutée en fin d'itération (après delivery gates, avant `_aretro_phase` — la retro E7 pourra ainsi digérer aussi les décisions de gouvernance). Méthode `Pipeline._agovern_phase()`.

**Entrée du PO** : observations routées `po` (statut ROUTED), méta-observations du Pattern Detector (F5), extraits pertinents de la mémoire (F4 : pending_ideas ouvertes, top dette), backlog actuel (epics/stories/statuts).

**Sortie** : liste de décisions JSON, une par observation :

```python
class GovernanceAction(str, Enum):
    CREATE_TASK = "create_task"        # TS technique rattachée à une story existante
    CREATE_STORY = "create_story"      # nouvelle US ou TS (technical=True, avec contract)
    CREATE_EPIC = "create_epic"        # + stories embryonnaires (statut TODO, itération suivante)
    UPDATE_STORY = "update_story"      # modifier description/priorité d'une story NON implémentée
    ENRICH_CRITERIA = "enrich_criteria" # ajouter des AC à une story NON implémentée
    DEFER = "defer"                    # → pending_ideas (mémoire F4) avec reevaluate_when
    PERSIST = "persist"                # → mémoire seule (component/architecture/debt/risk)
    DISMISS = "dismiss"                # ignorer, motif obligatoire

class GovernanceDecision(BaseModel):
    id: str; observation_id: str; action: GovernanceAction
    target_id: str = ""                # story/epic ciblée
    payload: dict = {}                 # contenu (story/task/AC à créer, champs à modifier)
    rationale: str
    status: str = "proposed"           # proposed | approved | applied | rejected_by_policy | rejected_by_human
    iteration: int = 0
```

`ProjectState.governance_log: list[GovernanceDecision] = []` — journal permanent (vision §2 : toute décision est traçable).

**Application déterministe** (`orchestrator/governance.py::apply_decision`) avec **garde-fous durs** (jamais confiés au LLM) :
- Interdit de modifier une story `DONE`/`GREEN` ou ses AC → converti automatiquement en `CREATE_STORY` (story de refactoring/évolution qui référence l'originale). Les AC d'une story livrée sont un contrat vérifié ; on n'en réécrit pas l'histoire.
- Interdit de supprimer des AC (seulement enrichir). L'affaiblissement de spec reste du ressort exclusif du workflow Amendment W5.1 existant.
- Quotas par itération : `GOVERN_MAX_NEW_STORIES=3`, `GOVERN_MAX_NEW_EPICS=1`, `GOVERN_MAX_UPDATES=5` (anti-emballement, vision §20 « comment limiter les discussions inter-agents »).
- Les créations passent par les validateurs existants du PO pipeline (schéma, intégrité référentielle, cycles — réutiliser les fonctions de `plan_pipeline.py`).
- Chaque application est gated par le Policy Engine F6 (niveau < 4 → `status="proposed"`, file d'approbation humaine).

Les stories créées portent `iteration = state.iteration + 1` et sont prises en compte au cycle suivant (réutilise le mécanisme « Continue Build » existant de E2). Les décisions `DEFER`/`PERSIST` écrivent dans la mémoire F4. Après gouvernance, les observations passent en statut `ACTIONED`/`PERSISTED`/`DEFERRED`/`DISMISSED` avec `resolution`.

**Réévaluation des idées en suspens** : au début de chaque `_agovern_phase`, les `pending_ideas` dont `reevaluate_when` est plausiblement atteint (jugé dans le même appel PO) sont réinjectées dans le lot à décider.

**Config** : `GOVERNANCE=0|1` (défaut 0, requiert `OBSERVATIONS=1`), quotas ci-dessus, `GOVERN_ROLE_TIER=boss` (décision de backlog = tier fort).

**Découpage** :
- **US-F3.1** Modèles décisions + phase GOVERN squelette (no-op flag OFF). *AC : la phase s'insère dans `_alifecycle` sans perturber l'existant ; état legacy chargeable.*
- **US-F3.2** Prompt `po_govern()` + persona `po-governor` : contexte = observations + backlog + mémoire ; sortie JSON décisions. *AC : sortie malformée → itération se termine sans décision (fail-open) ; log.*
- **US-F3.3** `apply_decision()` déterministe + garde-fous + quotas. *AC (critiques) : UPDATE sur story DONE → converti en CREATE_STORY ; suppression d'AC impossible ; quotas respectés ; stories créées valides (ids uniques, epic existant, pas de cycle de dépendances).*
- **US-F3.4** Intégration policy F6 + file d'approbation : endpoints `GET/POST /api/projects/{id}/governance/decisions/{did}/approve|reject`. *AC : niveau autonomie < 4 → rien n'est appliqué sans approbation ; approbation → application + événement.*
- **US-F3.5** Cycle suivant : stories gouvernées visibles au plan/build de l'itération N+1 ; `pending_ideas` réévaluées. *AC : test d'intégration bout-en-bout avec FakeRunner scripté (observation → décision create_story → story construite à l'itération suivante).*

**Fichiers** : `orchestrator/governance.py` (nouveau), `models.py`, `prompts.py`, `personas.py`, `pipeline.py` (phase), `api/server.py` (endpoints), `config.py`, tests `tests/test_governance.py`.

---

### V3-F4 — Mémoire logicielle multi-niveaux (Software Knowledge Base)

**But** : persister la connaissance qui ne doit PAS devenir une tâche (vision §11) et la **réinjecter** aux bons agents au bon moment.

**Nouveau module** : `orchestrator/knowledge.py`, fichier par projet `autospec-knowledge.json` (à côté de `autospec-state.json`, même pattern d'écriture atomique). Hors de `ProjectState` volontairement : cycle de vie différent (survit aux itérations, croît lentement, compaction propre).

```python
class KnowledgeBase(BaseModel):
    component_memory: dict[str, list[MemoryEntry]]  # clé = stream/composant
    architecture_notes: list[MemoryEntry]
    adrs: list[ADR]              # id, title, decision, context, status(proposed|accepted|superseded), source_observation_id
    debt_register: list[DebtEntry]    # + effort_estimate, interest("s'aggrave si…")
    risk_register: list[RiskEntry]    # + likelihood, mitigation
    pending_ideas: list[PendingIdea]  # + value_hint, reevaluate_when, source_observation_id
```

Chaque entrée garde `source_observation_id`, `iteration`, `created_at` — traçabilité complète observation → mémoire.

**Écriture** : uniquement via le Router F2 et le PO F3 (le Coding Agent n'écrit jamais directement dans la mémoire — vision §9). Les ADRs `proposed` sont validés par l'architecte au prochain `_aarchitect_phase` (accepted/superseded).

**Injection (le point qui rend la mémoire utile)** :
- **Dev** (`dev_revise`) : bloc `knowledge_block(stream)` — component_memory du stream ciblé + contraintes + workarounds actifs, plafonné à `KNOWLEDGE_INJECT_MAX=10` entrées les plus récentes/urgentes.
- **PO** (plan + govern) : pending_ideas ouvertes, top-5 dette par urgence, risques `high`.
- **Architecte** : ADRs acceptés + architecture_notes.
- **QA** : entrées `constraint`/`limitation` du stream (évite de re-tester l'impossible).

**Compaction** : au-delà de `KNOWLEDGE_MAX_PER_SECTION=50`, appel worker tier de fusion/synthèse (même philosophie que les lessons F1 existantes).

**API** : `GET /api/projects/{id}/knowledge`, `PATCH .../knowledge/{section}/{entry_id}` (édition/suppression humaine).

**Découpage** :
- **US-F4.1** Modèles + persistance + load/save atomique + API lecture. *AC : round-trip ; fichier absent → base vide ; écriture atomique.*
- **US-F4.2** Écritures depuis Router F2 (debt/risk/architecture/discovery) et PO F3 (persist/defer). *AC : une observation routée `debt` crée une DebtEntry tracée.*
- **US-F4.3** Injection dans prompts (dev/po/architect/qa) avec plafonds. *AC : le bloc n'apparaît que si non vide ; jamais > plafond ; flag OFF → prompts identiques à avant (comparaison golden).*
- **US-F4.4** Compaction + endpoints d'édition. *AC : dépassement → fusion ; entrée supprimée n'est plus injectée.*

**Config** : `KNOWLEDGE=0|1` (défaut 0 ; auto-activé par `GOVERNANCE=1`), plafonds ci-dessus.

**Fichiers** : `orchestrator/knowledge.py` (nouveau), `prompts.py` (blocs), `api/server.py`, `config.py`, tests `tests/test_knowledge.py`.

---

### V3-F5 — Pattern Detector (agent ambient)

**But** : détecter tendances et accumulations que personne ne voit tâche par tâche (vision §12–§13).

**Déclenchement événementiel** (pas de boucle LLM permanente — vision §13) : à la fin de chaque itération (hook avant `_agovern_phase`, pour que le PO reçoive les méta-observations du même cycle) et seulement si ≥ `PATTERN_MIN_SIGNALS=5` nouveaux signaux depuis la dernière exécution.

**Entrées (déjà toutes disponibles)** : `state.observations` (dont fusions/récurrences du critic F2), `guard_findings` par story, `calibration_by_iteration` (attempts, splits, escalades), KPIs `scorecard.py`, registre de dette F4.

**Étage déterministe d'abord** : agrégats par stream/composant — taux d'échec 1ère tentative, nb d'observations par type, dette cumulée, récurrence de doublons. Seuils configurables → candidats.
**Étage LLM (boss tier, 1 appel)** : sur les candidats uniquement, formule des méta-observations `type=PATTERN` (ex. « le stream frontend concentre 70 % des wrong-test ; recommander une TS d'harmonisation des fixtures ») avec preuves chiffrées.

Les méta-observations repassent par le Router F2 (destination `po` + `architecture`) et sont donc gouvernées comme les autres — le detector **propose**, ne décide pas.

**Découpage** :
- **US-F5.1** Agrégateur déterministe (pur, testable). *AC : agrégats corrects sur un état synthétique de 3 itérations.*
- **US-F5.2** Prompt `pattern_detect()` + hook itération + routage des méta-observations. *AC : < seuil de signaux → zéro appel LLM ; méta-observation arrive dans la file de gouvernance.*

**Config** : `PATTERN_DETECTOR=0|1` (défaut 0), `PATTERN_MIN_SIGNALS=5`.
**Fichiers** : `orchestrator/pattern_detector.py` (nouveau), `prompts.py`, `personas.py`, `pipeline.py` (hook), tests `tests/test_pattern_detector.py`.

---

### V3-F6 — Policy Engine d'autonomie

**But** : niveaux d'autonomie 0–5, Recommended vs Effective (vision §4), en remplacement des gates binaires épars.

**Nouveau module** : `orchestrator/policy.py`.

```python
class Decision(str, Enum):
    ALLOW = "allow"; REQUIRE_HUMAN = "require_human"; DENY = "deny"

DOMAINS = ["backlog_changes",   # F3 create/update
           "spec_amendments",   # W5.1 (remplace AMENDMENT_AUTO)
           "memory_writes",     # F4
           "delivery",          # docker deploy
           "next_feature"]      # auto-spec : choix de l'hypothèse suivante

def decide(domain: str, action: str, state: ProjectState, evidence: dict) -> Decision: ...
```

- **Recommended autonomy** : `AUTONOMY_LEVEL=2` global + overrides `AUTONOMY_<DOMAIN>`.
- **Effective autonomy** : le moteur **rétrograde** (jamais ne promeut) selon des signaux déterministes : guard findings récents (`-1` niveau), ≥ 2 échecs d'arbitrage dans l'itération (`-1`), budget consommé > 80 % (`-1` sur backlog_changes), première itération d'un projet (`-1`). Journal des rétrogradations dans `state.autonomy_log` (traçabilité).
- Mapping des niveaux : 0–1 → `REQUIRE_HUMAN` partout ; 2–3 → `REQUIRE_HUMAN` sur backlog_changes/spec_amendments, `ALLOW` memory_writes ; 4 → `ALLOW` si les juges/critics ont validé (verdicts joints dans `evidence`) ; 5 → `ALLOW`.
- **Migration douce** : `AMENDMENT_AUTO=1` existant est lu comme `AUTONOMY_SPEC_AMENDMENTS=5` (compat conservée) ; le gate composants existant devient un appel `decide("delivery", "setup_components", …)`.
- File d'approbations unifiée : `state.pending_approvals` (amendements W5.1 + décisions F3 + déploiements) + endpoints + événement SSE `approval_pending`.

**Découpage** :
- **US-F6.1** Moteur `decide()` pur + rétrogradations + log. *AC : table de vérité niveaux×domaines testée ; signaux → rétrogradation correcte ; jamais de promotion.*
- **US-F6.2** Branchements : F3 (déjà prévu US-F3.4), W5.1 amendment, docker delivery, auto-spec next-feature. *AC : compat `AMENDMENT_AUTO` ; comportement inchangé si `AUTONOMY_LEVEL` non défini (défaut = équivalent actuel).*
- **US-F6.3** File d'approbations unifiée + endpoints. *AC : approbation/refus appliqués et journalisés.*

**Config** : `AUTONOMY_LEVEL=2` (défaut = comportement actuel human-gated), `AUTONOMY_<DOMAIN>`.
**Fichiers** : `orchestrator/policy.py` (nouveau), `pipeline.py` (points d'appel), `amendment.py`, `api/server.py`, `config.py`, tests `tests/test_policy.py`.

---

### V3-F7 — UI Observations, Gouvernance & Mémoire

**But** : rendre la boucle visible et pilotable (sinon la gouvernance human-gated est inutilisable).

- **ObservationsPanel** : liste filtrable (type, statut, stream, itération), badge urgence, détail extensible (preuves, recommandations, décision PO liée). Suit le pattern de `BacklogPanel`.
- **GovernancePanel** : décisions en attente (`proposed`) avec boutons Approuver/Rejeter, diff lisible du backlog (« + US-12 “…” dans EPIC-3 », « AC-4 ajouté à US-7 »), journal des décisions passées avec rationale.
- **KnowledgePanel** : onglets ADRs / Dette / Risques / Idées en suspens ; édition/suppression (US-F4.4) ; lien vers l'observation source.
- **Badges** : compteur d'approbations en attente dans `ProjectBar` (pulsation comme l'existant) ; événements SSE `observation`, `governance_decision`, `approval_pending` déjà émis par F1/F3/F6.

**Découpage** : **US-F7.1** client API + types TS (miroir des modèles) ; **US-F7.2** ObservationsPanel ; **US-F7.3** GovernancePanel + actions approve/reject ; **US-F7.4** KnowledgePanel ; **US-F7.5** badges + événements temps réel. Tests Vitest par composant (pattern existant), pas de nouveau test e2e requis.

**Fichiers** : `frontend/src/api.ts`, `frontend/src/components/ObservationsPanel.tsx` (+Governance/Knowledge), `App.tsx`/`Dashboard` (onglets), tests `.test.tsx`.

---

### V3-F8 — Codebase Cartographer (lot 3, optionnel)

**But** : carte locale du code (composants, dépendances, conventions, fichiers concernés, risques — vision §5) pour fiabiliser le planning technique et le brownfield.

- **Étage déterministe** : analyse d'imports Python (AST) + imports TS (regex) → graphe modules/dépendances, top fan-in (fichiers « chauds »), tailles. Nouveau module `orchestrator/cartographer.py`.
- **Étage LLM (worker)** : résumé par composant (rôle, conventions observées) stocké dans `component_memory` (F4) — le cartographe **écrit dans la mémoire existante**, pas de nouveau store.
- **Usage** : rafraîchi en début d'itération (si `git diff` non vide depuis la dernière carte) ; injecté au PO pipeline S1 (aide au sizing/`files_hint`) et au Dev (fichiers chauds = prudence). Particulièrement utile en profil `brownfield`.

**Découpage** : **US-F8.1** graphe déterministe + tests ; **US-F8.2** résumés LLM → component_memory ; **US-F8.3** injection S1 + dev.
**Config** : `CARTOGRAPHER=0|1` (défaut 0). Dépend de F4.

---

## 3. Ce que V3 ne fait PAS (écarté volontairement)

- **Decision Aggregator multi-évaluateurs** (vision §6) : la recovery machine W1 + arbitrage W2 couvrent déjà Retry/Revise/Abort au niveau tâche. Redondant aujourd'hui.
- **Gouvernance d'entreprise** (vision §15 : Strategy/Portfolio/Budget Authority) et **Product Discovery quantitatif** (§16 : Analytics/Experiment) : nécessitent des données d'usage réel qu'Autospec ne collecte pas. Hors périmètre V3.
- **Exploitation** (§17 : SRE/Incident/Cost Optimizer) : Autospec livre des projets, il ne les opère pas en continu.
- **Réécriture du workflow par le système lui-même** (§18) : la structure des phases reste fixe ; seule la politique change (conforme à la vision §1 : « le workflow est invariant ; seule la politique d'exécution change »).
- **Mémoire versionnée git** (question ouverte §20) : le JSON + journaux tracés suffisent ; à revoir si besoin de diff/rollback de mémoire.

---

## 4. Plan d'implémentation

**Ordre imposé par les dépendances** (models/pipeline/prompts sont des hot-paths partagés → lots séquentiels, pas de parallélisation sauvage) :

| Lot | Contenu | Dépend de |
|---|---|---|
| **Lot 1a** | F1 (observations socle) | — |
| **Lot 1b** | F2 (critic + router) + F4 (mémoire, US-F4.1/F4.2) | F1 |
| **Lot 1c** | F3 (gouvernance PO) + F4 (injection US-F4.3/F4.4) | F1, F2, F4.1 |
| **Lot 2a** | F6 (policy engine) — brancher F3 dessus | F3 |
| **Lot 2b** | F5 (pattern detector) | F1, F2, F4 |
| **Lot 3a** | F7 (frontend) — parallélisable avec 2b (fichiers disjoints) | endpoints F3/F4/F6 |
| **Lot 3b** | F8 (cartographer) — optionnel | F4 |

**Definition of Done par lot** : tests unitaires du lot verts + suite backend complète verte (`uv run pytest` dans `backend/`) + flag OFF ⇒ aucun changement de comportement observable (les tests existants passent inchangés) + test d'intégration FakeRunner du chemin nominal du lot.

**Test d'intégration final V3** (après Lot 2a) : scénario scripté complet — un work item échoue avec workaround → observation extraite → validée/routée → PO décide `create_story` (TS) → policy `REQUIRE_HUMAN` → approbation API → story appliquée itération N+1 → dette persistée en mémoire → injectée au prompt dev suivant.
