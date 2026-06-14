"""Task prompts sent to the BMAD agents (the personas are the system prompts)."""

from __future__ import annotations

import json

from ..models import FeatureHypothesis, HypothesisStatus, ProjectState, UserStory

# --------------------------------------------------------------- shared helpers

def _convo(state: ProjectState) -> str:
    """Render the recent chat history for a PM/analyst prompt."""
    return "\n".join(f"[{m.role.value}] {m.content}" for m in state.chat[-30:]) or "(aucune)"


def _feedback(state: ProjectState) -> str:
    """Render the recent user feedback as a bullet list."""
    return "\n".join(f"- {f}" for f in state.feedback[-10:]) or "(aucun)"


def _criteria_block(story: UserStory) -> str:
    """Render acceptance criteria as '- [AC-n] text' lines (ids referenced by QA)."""
    return "\n".join(f"- [{c.id}] {c.text}" for c in story.acceptance_criteria)


def _snake(story_id: str) -> str:
    """Story id as a python-friendly file fragment ('US-1' -> 'us_1')."""
    return story_id.lower().replace("-", "_")


# ----------------------------------------------- Refinement harness (critic/judge)

def critic_review(kind: str, artifact: str, criteria: str) -> str:
    return f"""On te soumet {kind} à critiquer dans une boucle de raffinement.

Travaille en mode ReAct (REFLECT puis ACT) :
1. REFLECT — décompose le travail en sous-aspects et analyse chacun au regard
   des critères de qualité ci-dessous (raisonnement explicite, étape par étape).
2. ACT — propose des améliorations CONCRÈTES et actionnables (pas de
   généralités). Ne réécris pas le travail toi-même.

Critères de qualité :
{criteria}

Élément à critiquer :
\"\"\"{artifact}\"\"\"

Réponds avec EXACTEMENT UN objet JSON :
{{"reflection": "<ton raisonnement décomposé, en français>", "issues": ["problème concret", "..."], "suggestions": ["amélioration actionnable", "..."]}}
Si l'élément est déjà excellent, renvoie des listes "issues"/"suggestions" vides."""


def judge_quality(kind: str, artifact: str, criteria: str) -> str:
    return f"""Tu es le juge qualité d'une boucle de raffinement. On te soumet {kind}.
Évalue objectivement sa qualité au regard des critères ci-dessous et donne une
note ENTIÈRE de 0 à 100 (100 = irréprochable, prêt à livrer). Sois exigeant mais
juste : la note pilote l'arrêt de la boucle.

Critères de qualité :
{criteria}

Élément à évaluer :
\"\"\"{artifact}\"\"\"

Réponds avec EXACTEMENT UN objet JSON :
{{"score": <entier 0-100>, "verdict": "<une phrase en français>", "reasons": ["..."]}}"""


PLAN_CRITERIA = (
    "- Chaque US suit INVEST (indépendante, négociable, valeur, estimable, "
    "petite, testable).\n"
    "- Critères d'acceptance précis, non ambigus et réellement testables.\n"
    "- Gherkin exécutable et aligné sur les critères.\n"
    "- Découpage en epics/US cohérent avec la complexité (ni trop gros, ni "
    "sur-découpé).\n"
    "- Dépendances et priorités kanban correctes et minimales."
)

CODE_CRITERIA = (
    "- Le code respecte les critères d'acceptance et fait passer toute la suite.\n"
    "- Séparation des responsabilités (SoC), fonctions courtes, nommage clair.\n"
    "- Pas de duplication (DRY), gestion des cas limites et des erreurs.\n"
    "- Tests lisibles couvrant les comportements clés, pas seulement le chemin "
    "nominal."
)


def po_revise(state: ProjectState, package_name: str, previous_json: str, critique: str) -> str:
    return f"""{po_plan(state, package_name)}

⚠️ BOUCLE DE RAFFINEMENT — une première version du plan a été produite puis
critiquée. Voici la version précédente (JSON) :
{previous_json}

Critique et améliorations à intégrer :
{critique}

Produis une VERSION AMÉLIORÉE du plan qui intègre ces retours, dans le format
JSON EXACT demandé ci-dessus (mêmes clés)."""


def dev_revise(
    story: UserStory,
    package_name: str,
    feature_rel_path: str,
    critique: str,
    architecture: str = "",
    guidance: str = "",
    lessons: str = "",
) -> str:
    return f"""{dev_story(story, package_name, feature_rel_path, architecture, guidance, lessons=lessons)}

⚠️ BOUCLE DE RAFFINEMENT — le code de cette story passe déjà au vert, mais un
critique a relevé des points d'amélioration :
{critique}

Améliore le code en intégrant ces retours. CONTRAINTE ABSOLUE : toute la suite
`uv run pytest` doit RESTER verte après tes modifications. Réponds avec le même
objet JSON que précédemment."""


# ---------------------------------------------------------------- PM (spec)

PM_ENVELOPE = """
Réponds avec EXACTEMENT UN objet JSON de l'une de ces deux formes :
{"type": "question", "message": "<ta ou tes questions à l'utilisateur, en français>"}
ou, quand tu as assez d'éléments pour rédiger le brief :
{"type": "brief", "message": "<court message de conclusion>", "brief": "<brief produit complet en markdown : contexte, problème, objectifs, périmètre MVP, hors périmètre, contraintes techniques>"}
"""


SPEC_DIMENSIONS = (
    "1) Problème & pourquoi — le job-to-be-done, la douleur réelle, ce qui se "
    "passe sans la feature.\n"
    "2) Utilisateurs / personas et leurs objectifs.\n"
    "3) Périmètre MVP — le plus petit incrément qui valide l'hypothèse.\n"
    "4) Hors-périmètre explicite.\n"
    "5) Contraintes — techniques, légales, délais, existant.\n"
    "6) Données & entités manipulées.\n"
    "7) Vues / écrans / parcours UX clés.\n"
    "8) Cas limites & règles métier.\n"
    "9) Critères de succès mesurables."
)


def pm_interview(state: ProjectState) -> str:
    auto = ""
    if state.auto_spec:
        auto = (
            "\nMODE AUTO-SPEC ACTIF : ne pose AUCUNE question à l'utilisateur. "
            "Prends toi-même toutes les décisions de spécification (choix "
            "raisonnables et minimalistes) et produis le brief immédiatement "
            '(type "brief").'
        )
    return f"""Tu es le PM, facilitateur en mode SOCRATIQUE. L'utilisateur veut créer :
\"\"\"{state.goal}\"\"\"

Conversation jusqu'ici :
{_convo(state)}

Ta mission : faire ÉMERGER une spécification claire en QUESTIONNANT, sans
présumer à la place de l'utilisateur. Procède dimension par dimension (pose 2-3
questions ciblées par tour, sur la dimension la moins claire), en pointant
différents niveaux — vision, parcours utilisateur, mécanisme, détail :
{SPEC_DIMENSIONS}
Reformule ce que tu comprends et confronte (« pourquoi ? », « et si… ? », « un
exemple concret ? ») pour révéler les non-dits et les hypothèses implicites.
Dès que les dimensions essentielles sont suffisamment claires, produis le brief.{auto}
{PM_ENVELOPE}"""


def pm_brainstorm(state: ProjectState) -> str:
    auto = ""
    if state.auto_spec:
        auto = (
            "\nMODE AUTO-SPEC : ne pose pas de question ; explore brièvement les "
            "options toi-même, choisis la plus pertinente et produis le brief."
        )
    return f"""Tu es Mary, analyste (méthode BMAD), en session de BRAINSTORMING. Ici on
re-questionne LE BESOIN lui-même (pas seulement les détails). Idée initiale :
\"\"\"{state.goal}\"\"\"

Conversation jusqu'ici :
{_convo(state)}

Méthode en deux temps :
- DIVERGER : élargis l'espace des possibles — angles différents, analogies,
  inversion du problème (« et si on faisait l'inverse ? »), jobs-to-be-done
  alternatifs, segments d'utilisateurs négligés, ce que ferait un concurrent.
  Propose PLUSIEURS pistes/options à l'utilisateur, formulées clairement.
- CONVERGER : aide-le à choisir et prioriser selon valeur / effort / risque.
Pose des questions ouvertes qui font réfléchir à plusieurs niveaux (vision,
utilisateur, mécanisme, détail). Reste concis. Quand le besoin est reformulé et
qu'une direction est choisie, produis le brief.{auto}
{PM_ENVELOPE}"""


# ------------------------------------------------------------ Analyst (explore)

def analyst_explore(state: ProjectState) -> str:
    delivered = [s.title for s in state.stories if s.status.value == "done"]
    failed = [s.title for s in state.stories if s.status.value == "failed"]
    carried = [
        {"id": h.id, "title": h.title, "rationale": h.rationale,
         "value": h.value, "complexity": h.complexity}
        for h in state.backlog
        if h.status in (HypothesisStatus.PROPOSED, HypothesisStatus.REJECTED)
    ]
    shipped = [
        {"id": h.id, "title": h.title}
        for h in state.backlog
        if h.status == HypothesisStatus.DONE
    ]
    return f"""Tu es l'analyste/explorateur d'un pipeline automatisé d'amélioration continue.

Produit — objectif initial :
\"\"\"{state.goal}\"\"\"

Brief de la dernière itération livrée :
\"\"\"{state.brief}\"\"\"

User stories livrées : {json.dumps(delivered, ensure_ascii=False)}
User stories en échec (à éviter ou à reformuler) : {json.dumps(failed, ensure_ascii=False)}
Hypothèses déjà livrées (NE PAS reproposer) : {json.dumps(shipped, ensure_ascii=False)}
Backlog d'hypothèses existant (à réévaluer, garder, amender ou rejeter) :
{json.dumps(carried, ensure_ascii=False)}
Feedback utilisateur récent (priorité absolue s'il y en a) :
{_feedback(state)}

Ta mission :
1. EXPLORE : formule 3 à 6 hypothèses de prochaines features (nouvelles ou
   reprises du backlog existant), chacune avec un rationale court.
2. ÉVALUE : note chaque hypothèse — value (1=faible..5=forte valeur
   utilisateur) et complexity (1=triviale..5=difficile).
3. PRIORISE : ordonne les hypothèses (mode kanban, pas de sprint) — la
   meilleure combinaison valeur/complexité/risque en premier. Le feedback
   utilisateur passe avant tout le reste.
4. DÉCIDE : choisis l'hypothèse à développer maintenant.

Réponds avec EXACTEMENT UN objet JSON :
{{
  "message": "<une phrase en français expliquant ta décision>",
  "hypotheses": [
    {{"id": "FH-1", "title": "...", "rationale": "...", "value": 4, "complexity": 2}}
  ],
  "selected": "<id de l'hypothèse choisie>"
}}
Les hypothèses doivent être ordonnées par priorité décroissante (la première =
la prochaine à développer = celle de "selected")."""


def pm_brief_for_feature(state: ProjectState, hypothesis: FeatureHypothesis) -> str:
    return f"""Tu es le PM d'un pipeline automatisé en boucle d'amélioration continue.

Produit existant — objectif initial :
\"\"\"{state.goal}\"\"\"

Brief de l'itération précédente :
\"\"\"{state.brief}\"\"\"

L'analyste a priorisé le backlog et choisi la prochaine feature à développer :
- Titre : {hypothesis.title}
- Rationale : {hypothesis.rationale}
- Valeur estimée : {hypothesis.value}/5 — Complexité estimée : {hypothesis.complexity}/5

Feedback utilisateur récent :
{_feedback(state)}

Ta mission : rédige le brief produit de CETTE feature (et seulement celle-ci),
petit et livrable, sans poser de question.
Réponds avec EXACTEMENT UN objet JSON :
{{"type": "brief", "message": "<une phrase de contexte>", "brief": "<brief markdown de la feature>"}}"""


# ------------------------------------------------------ Feedback impact (E2)

def feedback_impact(state: ProjectState, feedback: str) -> str:
    stories = [
        {
            "id": s.id,
            "epic_id": s.epic_id,
            "title": s.title,
            "status": s.status.value,
            "implemented": s.status.value in ("done", "green"),
        }
        for s in state.stories
    ]
    epics = [{"id": e.id, "title": e.title} for e in state.epics]
    return f"""Tu es l'analyste d'impact d'un pipeline automatisé. L'utilisateur vient de
donner un feedback / une demande de changement sur le produit :
\"\"\"{feedback}\"\"\"

Objectif initial du produit :
\"\"\"{state.goal}\"\"\"

Brief de la dernière itération :
\"\"\"{state.brief}\"\"\"

Epics existants : {json.dumps(epics, ensure_ascii=False)}
User stories existantes (champ "implemented" = déjà codée) :
{json.dumps(stories, ensure_ascii=False)}

Ta mission : ANALYSER L'IMPACT de ce feedback et DÉCIDER :
- "update_story" : le feedback amende une story EXISTANTE et NON IMPLÉMENTÉE
  (status "todo" ou "failed" uniquement) → fournis "story_id" + "updates"
  (seuls les champs à changer).
- "new_stories" : le feedback est une nouvelle tâche (ou touche une story déjà
  implémentée, qu'on ne réécrit pas) → fournis l'epic (existant via "epic_id",
  ou nouveau via "epic") et les nouvelles stories au format PO.
- "none" : le feedback est une simple remarque sans travail à planifier.

Réponds avec EXACTEMENT UN objet JSON :
{{
  "message": "<explication de ta décision, en français>",
  "action": "update_story" | "new_stories" | "none",
  "story_id": "<si update_story>",
  "updates": {{"title": "...", "description": "...", "acceptance_criteria": ["..."], "gherkin": "...", "priority": 3}},
  "epic_id": "<si new_stories et epic existant>",
  "epic": {{"id": "EPIC-X", "title": "...", "description": "..."}},
  "stories": [
    {{"id": "US-X", "title": "...", "description": "En tant que..., je veux..., afin de...",
      "acceptance_criteria": ["..."], "gherkin": "Feature: ...", "depends_on": [], "priority": 2}}
  ]
}}
N'inclus que les clés utiles à l'action choisie. Pour "updates", n'inclus QUE
les champs réellement modifiés."""


# ------------------------------------------------------ Product evaluator (E6)

def evaluator_probe(state: ProjectState, package_name: str, run_output: str) -> str:
    delivered = [
        {"id": s.id, "title": s.title}
        for s in state.stories
        if s.status.value == "done"
    ]
    return f"""Tu es l'évaluateur d'un pipeline automatisé. Le répertoire courant contient le
code GÉNÉRÉ du produit « {state.name} » (package Python `{package_name}`, projet
uv, lancé via `uv run python main.py`, tests via `uv run pytest`).

Brief produit :
\"\"\"{state.brief}\"\"\"

Fonctionnalités censées être livrées (vertes sous pytest) :
{json.dumps(delivered, ensure_ascii=False)}

Sortie observée au lancement réel de l'application (`main.py`) :
\"\"\"{run_output[-4000:]}\"\"\"

Ta mission : EXERCER RÉELLEMENT le produit pour trouver ce que les tests
unitaires n'attrapent pas. Lis les fichiers du répertoire courant (code, main.py,
tests) et confronte-les au brief et à la sortie d'exécution ci-dessus. Cherche :
- des BUGS passés sous pytest (comportement faux, sortie incohérente, crash au
  lancement réel) ;
- des INTÉGRATIONS cassées entre stories (deux features qui ne se composent pas) ;
- des FRICTIONS UX (parcours confus, messages peu clairs) ;
- des MANQUES par rapport au brief (capacité attendue absente).
Ne signale QUE des problèmes concrets et étayés par ce que tu observes — pas de
spéculation. Si le produit semble correct, renvoie une liste "findings" vide.

Réponds avec EXACTEMENT UN objet JSON :
{{
  "message": "<une phrase en français résumant ton évaluation>",
  "findings": [
    {{"id": "FND-1", "severity": "high|medium|low", "kind": "bug|integration|ux|gap",
      "title": "<résumé court>", "detail": "<description précise et reproductible>"}}
  ]
}}"""


def security_review_probe(state: ProjectState, package_name: str, audit_output: str) -> str:
    return f"""Tu es l'auditeur sécurité d'un pipeline automatisé. Le répertoire courant
contient le code GÉNÉRÉ du produit « {state.name} » (package Python `{package_name}`,
projet uv).

Brief produit :
\"\"\"{state.brief}\"\"\"

Rapport d'audit des dépendances (pip-audit / npm audit — peut être vide ou indisponible) :
\"\"\"{audit_output[-4000:]}\"\"\"

Ta mission : AUDITER LA SÉCURITÉ du code généré. Lis les fichiers du répertoire
courant (code, main.py) et cherche des faiblesses réelles et exploitables :
- injection (SQL/commande/template), désérialisation non sûre (pickle, yaml.load),
  `eval`/`exec`/`subprocess(shell=True)` sur entrée non validée ;
- traversée de chemin, lecture/écriture de fichier non bornée ;
- secrets en dur (clés, mots de passe, tokens) ;
- validation d'entrée manquante, auth/authz absente ou contournable ;
- dépendances vulnérables remontées par le rapport d'audit ci-dessus.
Ne signale QUE des problèmes concrets et étayés par ce que tu observes — pas de
spéculation. Si rien de notable, renvoie une liste "findings" vide.

Réponds avec EXACTEMENT UN objet JSON :
{{
  "message": "<une phrase en français résumant l'audit>",
  "findings": [
    {{"id": "SEC-1", "severity": "high|medium|low", "kind": "security",
      "title": "<résumé court>", "detail": "<faille précise + localisation + piste de correction>"}}
  ]
}}"""


# ------------------------------------------------- Solution agent (components)

def components_proposal(state: ProjectState) -> str:
    return f"""Tu es l'agent solutionneur d'un pipeline automatisé. Voici le brief produit :
\"\"\"{state.brief or state.goal}\"\"\"

Ta mission : proposer les COMPOSANTS techniques du produit à générer. Par
défaut, pars sur : un backend Python + FastAPI et un frontend React + Vite.
Ajoute en OPTIONNEL (optional=true) les composants d'infrastructure pertinents
(base de données PostgreSQL, cache Redis…) UNIQUEMENT si le brief les justifie.
Reste minimal : un produit purement CLI/librairie peut n'avoir qu'un backend.

Réponds avec EXACTEMENT UN objet JSON :
{{
  "message": "<une phrase en français justifiant la stack>",
  "components": [
    {{"id": "backend", "kind": "backend", "name": "API backend", "technology": "Python + FastAPI", "rationale": "...", "optional": false}},
    {{"id": "frontend", "kind": "frontend", "name": "Interface web", "technology": "React + Vite", "rationale": "...", "optional": false}},
    {{"id": "db", "kind": "database", "name": "Base de données", "technology": "PostgreSQL", "rationale": "...", "optional": true}}
  ]
}}
Les "kind" autorisés : backend, frontend, database, cache, other."""


# ------------------------------------------------------- Tech-writer (delivery)

def tech_writer(state: ProjectState, package_name: str) -> str:
    components = [
        {"kind": c.kind, "name": c.name, "technology": c.technology, "status": c.status.value}
        for c in state.components
    ]
    stories_done = [s.title for s in state.stories if s.status.value == "done"]
    return f"""Tu es le tech-writer d'un pipeline automatisé. Le répertoire courant contient
le code GÉNÉRÉ du produit « {state.name} » (package Python `{package_name}`,
projet uv, lancé via `uv run python main.py`, tests via `uv run pytest`).

Brief produit :
\"\"\"{state.brief}\"\"\"

Composants du produit : {json.dumps(components, ensure_ascii=False)}
Fonctionnalités livrées : {json.dumps(stories_done, ensure_ascii=False)}
Architecture (si définie) :
\"\"\"{state.architecture or "(non documentée)"}\"\"\"

Ta mission : rédige le README du PROJET GÉNÉRÉ (pas d'Autospec), en t'appuyant
sur les fichiers du répertoire courant si tu peux les lire. Le README doit
contenir : présentation du produit, fonctionnalités, instructions d'installation
ET de lancement (uv), comment exécuter les tests, et un résumé d'architecture
(modules/couches réels du code).

Réponds avec EXACTEMENT UN objet JSON :
{{"message": "<une phrase en français>", "readme": "<contenu markdown complet du README.md>"}}"""


# ---------------------------------------------------------- Architect (design)

def architect_design(state: ProjectState, package_name: str) -> str:
    titles = [s.title for s in state.stories_of_iteration(state.iteration)]
    stories = "\n".join(f"- {t}" for t in titles) or "(aucune)"
    return f"""Tu es l'architecte technique d'un pipeline automatisé. Voici le brief produit :
\"\"\"{state.brief}\"\"\"

Stories planifiées de l'itération courante :
{stories}

Ta mission : produis un design technique CONCIS pour le package `{package_name}`,
qui guidera le QA et le développeur. Pas de sur-ingénierie : juste assez pour
guider l'implémentation (architecture cible en couches/modules, composants clés,
conventions de nommage, contraintes transverses).

Réponds avec EXACTEMENT UN objet JSON :
{{"message": "<une phrase, français>", "design": "<markdown court : architecture cible (couches/modules), composants clés, conventions de nommage, contraintes transverses>"}}"""


# ---------------------------------------------------------------- PO (plan)

def po_plan(state: ProjectState, package_name: str) -> str:
    existing = [
        {"id": s.id, "title": s.title, "status": s.status.value}
        for s in state.stories
    ]
    return f"""Tu es le PO/Scrum Master d'un pipeline automatisé. Voici le brief produit :
\"\"\"{state.brief}\"\"\"

Stories déjà existantes dans le projet (itérations précédentes) :
{json.dumps(existing, ensure_ascii=False)}

Ta mission : découpe ce brief en 1 à 3 EPICs, chacune contenant 1 à 5 user
stories. Adapte la granularité à la complexité : une petite feature = 1 epic /
1-2 stories. Chaque story doit :
- avoir une description classique ("En tant que..., je veux..., afin de...") ;
- avoir des critères d'acceptance précis et testables ;
- avoir un test d'acceptance Gherkin (langue: français, mots-clés Gherkin
  anglais: Feature/Scenario/Given/When/Then) exécutable avec pytest-bdd contre
  du code Python du package `{package_name}` (teste des fonctions/classes
  Python, PAS d'interface graphique ni de réseau) ;
- déclarer ses dépendances vers d'autres stories via leurs ids quand l'ordre
  d'implémentation compte (les stories sans dépendance mutuelle pourront être
  implémentées en parallèle) ;
- avoir une priorité kanban `priority` (1=haute..5=basse) : pour les stories
  sans dépendance entre elles, c'est cette priorité qui décide l'ordre de
  passage en développement ;
- porter un drapeau `ui` (booléen) : true UNIQUEMENT si la story a une vraie
  dimension visuelle/interface (écran, rendu, interaction navigateur), false
  pour la logique pure / API / CLI.

Réponds avec EXACTEMENT UN objet JSON :
{{
  "epics": [
    {{
      "id": "EPIC-1",
      "title": "...",
      "description": "...",
      "stories": [
        {{
          "id": "US-1",
          "title": "...",
          "description": "En tant que..., je veux..., afin de...",
          "acceptance_criteria": ["...", "..."],
          "gherkin": "Feature: ...\\n  Scenario: ...\\n    Given ...\\n    When ...\\n    Then ...",
          "depends_on": [],
          "priority": 1,
          "ui": false
        }}
      ]
    }}
  ]
}}
Les ids doivent être uniques et les depends_on référencer des ids de stories de
ce même JSON (ou des stories existantes listées plus haut)."""


# ---------------------------------------------------------------- QA (test design)

def qa_test_plan(
    story: UserStory, package_name: str, architecture: str = "", lessons: str = ""
) -> str:
    arch_block = f"\nContexte architecture (à respecter) :\n{architecture}\n" if architecture else ""
    lessons_block = (
        f"\nLeçons des itérations précédentes (rétrospective d'usine — à appliquer) :\n{lessons}\n"
        if lessons
        else ""
    )
    return f"""Tu es l'architecte de tests d'un pipeline automatisé BDD/TDD. Le code sera du
Python dans le package `{package_name}` (projet uv, pytest + pytest-bdd).
{arch_block}{lessons_block}

User story à couvrir : {story.id} — {story.title}
Description : {story.description}
Critères d'acceptance (chacun avec son id entre crochets) :
{_criteria_block(story)}

Test d'acceptance fonctionnel (Gherkin, déjà écrit, NE PAS le modifier) :
\"\"\"{story.gherkin}\"\"\"

Ta mission : DÉCOMPOSER ce test d'acceptance en tests unitaires, en mode
outside-in / London school (top-down), AVANT toute implémentation :
- Le Gherkin garde la vision fonctionnelle de bout en bout.
- En dessous, chaque couche de l'architecture cible reçoit son ou ses tests
  unitaires : la couche externe (API/façade) appelle-t-elle bien la couche
  suivante ? le service appelle-t-il bien le repository, l'autre service, le
  client LLM, etc. ? Chaque test MOCKE ses collaborateurs directs.
- ADAPTE LA GRANULARITÉ à la taille de la story : story triviale (une fonction
  pure) → 0 à 2 tests unitaires suffisent ; story moyenne/grosse → décompose
  couche par couche (api → façade → service → repository/llm → domaine).
- Ordonne les tests du plus externe au plus interne (ordre d'écriture).
- RATTACHE chaque test au(x) critère(s) d'acceptance qu'il couvre, via leurs
  ids (champ "criteria"). Chaque critère doit être couvert par au moins un test.

Réponds avec EXACTEMENT UN objet JSON :
{{
  "message": "<une phrase en français résumant ta stratégie>",
  "tests": [
    {{
      "id": "UT-1",
      "layer": "service",
      "description": "le service X appelle le repository Y avec ... et retourne ...",
      "mocks": ["repository Y"],
      "file_hint": "tests/unit/test_{_snake(story.id)}_service.py",
      "criteria": ["AC-1"]
    }}
  ]
}}
Une liste "tests" vide est acceptable si le Gherkin seul suffit (story triviale)."""


# ---------------------------------------------------------------- Dev (build)

def _format_test_plan(story: UserStory) -> str:
    if not story.test_plan:
        return ""
    lines = []
    for test in story.test_plan:
        mocks = f" — mocks : {', '.join(test.mocks)}" if test.mocks else ""
        hint = f" [{test.file_hint}]" if test.file_hint else ""
        lines.append(f"- {test.id} (couche {test.layer}) : {test.description}{mocks}{hint}")
    return "\n".join(lines)


UI_TEST_BLOCK = """
TESTS D'ACCEPTANCE UI (story à dimension visuelle) :
Cette story a une dimension UI. EN PLUS de la suite pytest-bdd, écris un ou
plusieurs tests d'acceptance UI Playwright REJOUABLES dans `tests/ui/` :
- fichier `tests/ui/test_{snake}_ui.py`, fonctions marquées `@pytest.mark.ui` ;
- utilise la fixture `page` de pytest-playwright : navigue vers l'UI générée,
  effectue les clics/saisies du scénario, capture un screenshot
  (`page.screenshot(path="tests/ui/screenshots/{snake}.png")`) et ASSERT sur le
  rendu (`expect(page.locator(...)).to_be_visible()` / contenu textuel) ;
- si l'app à tester doit tourner, démarre-la dans une fixture (subprocess +
  attente du port) et arrête-la en teardown ;
- ces tests sont exclus de la suite par défaut (marker `ui`) et lancés via
  `uv run pytest -m ui` — ils doivent rester verts ET rejouables.
Liste ces fichiers dans la clé "ui_test_files" de ta réponse JSON finale.
"""


def dev_story(
    story: UserStory,
    package_name: str,
    feature_rel_path: str,
    architecture: str = "",
    guidance: str = "",
    ui_tests: bool = False,
    lessons: str = "",
) -> str:
    arch_block = f"\nContexte architecture (à respecter) :\n{architecture}\n" if architecture else ""
    guidance_block = (
        f"\nConsignes de l'utilisateur (à respecter en priorité) :\n{guidance}\n" if guidance else ""
    )
    lessons_block = (
        f"\nLeçons des itérations précédentes (rétrospective d'usine — à appliquer) :\n{lessons}\n"
        if lessons
        else ""
    )
    ui_block = UI_TEST_BLOCK.replace("{snake}", _snake(story.id)) if ui_tests else ""
    plan = _format_test_plan(story)
    plan_section = ""
    plan_step = ""
    if plan:
        plan_section = f"""
L'architecte QA a décomposé ce test d'acceptance en tests unitaires outside-in
(London school) — chaque test mocke ses collaborateurs directs :
{plan}
"""
        plan_step = """
2. Écris TOUS les tests unitaires du plan QA ci-dessus, dans l'ordre donné (du
   plus externe au plus interne), dans `tests/unit/` (respecte les file_hint).
   Mocke les collaborateurs directs indiqués (unittest.mock). N'implémente
   RIEN à ce stade : seuls les squelettes (interfaces/signatures) nécessaires
   pour que les tests s'importent ont le droit d'exister."""
    return f"""Tu es le développeur d'un pipeline automatisé BDD/TDD. Tu travailles dans le
répertoire courant, qui est un projet Python géré par uv (pyproject.toml déjà
présent, pytest + pytest-bdd installés).
{arch_block}{guidance_block}{lessons_block}
User story à implémenter : {story.id} — {story.title}
Description : {story.description}
Critères d'acceptance :
{_criteria_block(story)}

Le test d'acceptance Gherkin est déjà écrit dans `{feature_rel_path}` :
\"\"\"{story.gherkin}\"\"\"
{plan_section}{ui_block}
PROCESSUS OBLIGATOIRE (BDD puis TDD, outside-in) :
1. Écris les step definitions pytest-bdd dans `tests/steps/test_{_snake(story.id)}.py`
   en liant chaque Given/When/Then du fichier feature (utilise
   `from pytest_bdd import scenarios, given, when, then, parsers` et
   `scenarios("../../{feature_rel_path}")`).{plan_step}
{"3" if plan else "2"}. Lance `uv run pytest` et VÉRIFIE que les nouveaux tests ÉCHOUENT (rouge).
{"4" if plan else "3"}. Implémente le minimum nécessaire dans le package `{package_name}/`, couche
   par couche du haut vers le bas, pour faire passer les tests un à un. Ajoute
   des tests unitaires TDD si tu crées de la logique non couverte.
{"5" if plan else "4"}. Relance `uv run pytest` jusqu'à ce que TOUTE la suite soit verte (les tests
   des stories précédentes doivent rester verts).
{"6" if plan else "5"}. Mets à jour `main.py` (point d'entrée CLI du projet) pour exposer la
   nouvelle fonctionnalité si pertinent.

CONTRAINTES :
- Ne modifie JAMAIS les fichiers .feature ni autospec-state.json.
- Ne touche qu'aux fichiers de ce répertoire.
- Code et docstrings en anglais ; messages utilisateur en français.

Quand tu as terminé, réponds avec EXACTEMENT UN objet JSON :
{{
  "status": "green" | "failed",
  "summary": "<ce que tu as fait, en français>",
  "files": ["<fichiers créés/modifiés>"],
  "test_results": [
    {{"id": "<id du test du plan QA>", "status": "green" | "red", "nodeids": ["<chemin/fichier.py::nom_test>"]}}
  ]
}}
Dans "test_results", pour CHAQUE test du plan QA (id exact), donne aussi les
`nodeids` pytest EXACTS que tu as écrits pour ce test (format
`chemin/fichier.py::nom_de_la_fonction_de_test`, tel que pytest les rapporte) —
l'orchestrateur s'en sert pour relire l'état réel depuis l'exécution de pytest.
Ne réponds "green" (au niveau global) que si `uv run pytest` passe intégralement."""


# --------------------------------------------------- Factory retrospective (E7)

def retro_review(state: ProjectState) -> str:
    """Mine the iteration's build signals into durable lessons + tuning advice."""
    from ..config import settings

    stories = [
        {
            "id": s.id,
            "title": s.title,
            "status": s.status.value,
            "attempts": s.attempts,
            "quality_score": s.quality_score,
            "last_error": (s.last_error or "")[-400:],
        }
        for s in state.stories_of_iteration(state.iteration)
    ]
    u = state.usage
    signals = {
        "iteration": state.iteration,
        "plan_quality": state.plan_quality,
        "stories": stories,
        "usage": {
            "cost_usd": round(u.cost_usd, 4),
            "tokens": u.input_tokens + u.output_tokens,
            "agent_calls": u.agent_calls,
        },
        "config": {
            "refine_max_rounds": settings.refine_max_rounds,
            "refine_quality_threshold": settings.refine_quality_threshold,
            "max_parallel_devs": settings.max_parallel_devs,
            "dev_max_attempts": settings.dev_max_attempts,
        },
    }
    previous = "\n".join(f"- {l}" for l in state.lessons) or "(aucune)"
    return f"""Tu es l'agent de rétrospective d'un pipeline automatisé d'usine logicielle.
L'itération {state.iteration} vient de se terminer. Voici les SIGNAUX déjà
collectés pendant le build (ne suppose rien au-delà) :
{json.dumps(signals, ensure_ascii=False)}

Leçons durables déjà capitalisées sur les itérations précédentes :
{previous}

Ta mission, à partir de CES SIGNAUX uniquement :
1. LEÇONS : produis des leçons durables et ACTIONNABLES pour guider le QA et le
   développeur des prochaines itérations (ex. « mocker explicitement le client X
   évite les retries rouge→vert observés sur US-N »). Reprends/raffine les leçons
   précédentes encore pertinentes, écarte celles devenues obsolètes. Reste
   concis : des consignes, pas un récit.
2. RECOMMANDATIONS DE RÉGLAGE : repère les signaux problématiques (raffinement
   trop court/long vu les scores, parallélisme à ajuster, dépendance
   chroniquement en échec) et propose des réglages concrets.

Réponds avec EXACTEMENT UN objet JSON :
{{
  "message": "<une phrase en français>",
  "lessons": ["<leçon durable actionnable>", "..."],
  "recommendations": ["<recommandation de réglage>", "..."]
}}
Renvoie la liste COMPLÈTE des leçons à conserver (pas seulement les nouvelles) :
elle remplace la précédente. Listes vides acceptables si rien de notable."""
