"""Task prompts sent to the BMAD agents (the personas are the system prompts)."""

from __future__ import annotations

import json

from ..models import FeatureHypothesis, HypothesisStatus, ProjectState, UserStory

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
) -> str:
    return f"""{dev_story(story, package_name, feature_rel_path, architecture, guidance)}

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


def pm_interview(state: ProjectState) -> str:
    convo = "\n".join(f"[{m.role.value}] {m.content}" for m in state.chat[-30:])
    auto = ""
    if state.auto_spec:
        auto = (
            "\nMODE AUTO-SPEC ACTIF : ne pose AUCUNE question à l'utilisateur. "
            "Prends toi-même toutes les décisions de spécification (choix "
            "raisonnables et minimalistes) et produis le brief immédiatement "
            '(type "brief").'
        )
    return f"""Tu es le PM d'un pipeline automatisé. L'utilisateur veut créer :
\"\"\"{state.goal}\"\"\"

Conversation jusqu'ici :
{convo or "(aucune)"}

Ta mission : clarifier le besoin puis produire un brief produit. Pose au plus
2-3 questions par tour, et seulement si elles changent réellement le produit.
Dès que c'est suffisamment clair, produis le brief.{auto}
{PM_ENVELOPE}"""


# ------------------------------------------------------------ Analyst (explore)

def analyst_explore(state: ProjectState) -> str:
    delivered = [s.title for s in state.stories if s.status.value == "done"]
    failed = [s.title for s in state.stories if s.status.value == "failed"]
    feedback = "\n".join(f"- {f}" for f in state.feedback[-10:]) or "(aucun)"
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
{feedback}

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
    feedback = "\n".join(f"- {f}" for f in state.feedback[-10:]) or "(aucun)"
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
{feedback}

Ta mission : rédige le brief produit de CETTE feature (et seulement celle-ci),
petit et livrable, sans poser de question.
Réponds avec EXACTEMENT UN objet JSON :
{{"type": "brief", "message": "<une phrase de contexte>", "brief": "<brief markdown de la feature>"}}"""


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
  passage en développement.

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
          "priority": 1
        }}
      ]
    }}
  ]
}}
Les ids doivent être uniques et les depends_on référencer des ids de stories de
ce même JSON (ou des stories existantes listées plus haut)."""


# ---------------------------------------------------------------- QA (test design)

def qa_test_plan(story: UserStory, package_name: str, architecture: str = "") -> str:
    criteria = "\n".join(f"- [{c.id}] {c.text}" for c in story.acceptance_criteria)
    arch_block = f"\nContexte architecture (à respecter) :\n{architecture}\n" if architecture else ""
    return f"""Tu es l'architecte de tests d'un pipeline automatisé BDD/TDD. Le code sera du
Python dans le package `{package_name}` (projet uv, pytest + pytest-bdd).
{arch_block}

User story à couvrir : {story.id} — {story.title}
Description : {story.description}
Critères d'acceptance (chacun avec son id entre crochets) :
{criteria}

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
      "file_hint": "tests/unit/test_{story.id.lower().replace("-", "_")}_service.py",
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


def dev_story(
    story: UserStory,
    package_name: str,
    feature_rel_path: str,
    architecture: str = "",
    guidance: str = "",
) -> str:
    criteria = "\n".join(f"- [{c.id}] {c.text}" for c in story.acceptance_criteria)
    arch_block = f"\nContexte architecture (à respecter) :\n{architecture}\n" if architecture else ""
    guidance_block = (
        f"\nConsignes de l'utilisateur (à respecter en priorité) :\n{guidance}\n" if guidance else ""
    )
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
{arch_block}{guidance_block}
User story à implémenter : {story.id} — {story.title}
Description : {story.description}
Critères d'acceptance :
{criteria}

Le test d'acceptance Gherkin est déjà écrit dans `{feature_rel_path}` :
\"\"\"{story.gherkin}\"\"\"
{plan_section}
PROCESSUS OBLIGATOIRE (BDD puis TDD, outside-in) :
1. Écris les step definitions pytest-bdd dans `tests/steps/test_{story.id.lower().replace("-", "_")}.py`
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
