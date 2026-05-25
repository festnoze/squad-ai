# Product Requirements Document (PRD)

**Projet :** AI Project Manager
**Version :** V0 (MVP)
**Date :** 2026-04-10
**Auteur :** John (PM) — facilitation avec Etienne
**Statut :** Draft initial

---

## 1. Executive Summary

**AI Project Manager** est une application web locale qui permet à un Product Manager / Product Owner non-technicien de transformer une idée floue en un projet structuré, cadré et découpé par une IA conversationnelle, puis de suivre visuellement l'avancement de son implémentation par des agents de développement.

Le V0 se concentre exclusivement sur le **cœur de valeur conversationnel** : chatbot de cadrage + UI de visualisation et suivi. Les agents de développement sont **mockés** afin de valider l'hypothèse produit la plus risquée avant d'investir dans l'orchestration réelle (V1).

**One-liner :** *"Un Jira IA-first pour les PM qui n'ont pas d'équipe tech."*

---

## 2. Problem Statement

### 2.1 Le problème

Les Product Managers, Product Owners, solopreneurs et consultants fonctionnels savent **décrire ce qu'ils veulent** mais n'ont souvent ni les compétences techniques ni une équipe dev pour l'implémenter. Les outils IA existants (Claude, ChatGPT, Claude Code, Cursor) sont puissants mais :

- **Orientés développeurs** — Claude Code et Cursor supposent une maîtrise de la ligne de commande, du versioning, des IDE
- **Non structurants** — ChatGPT/Claude produisent des réponses linéaires sans visualisation, sans persistance structurée, sans suivi d'avancement
- **Sans vue projet** — aucun ne propose de vision globale du projet (backlog, statuts, découpage) accessible à un non-technicien

Résultat : le PM non-tech se retrouve soit à **bricoler** des listes markdown dans Notion, soit à **demander à un dev** de faire le lien entre lui et l'IA, soit à **abandonner** l'idée faute de traction technique.

### 2.2 L'opportunité

Il existe une asymétrie croissante : les IA de code (Claude Code, Cursor, Devin) sont capables d'implémenter des features à partir de specs bien écrites, mais **personne ne fournit aux non-tech l'interface qui produit ces specs et qui les fait exécuter visuellement**.

AI Project Manager comble ce gap : il transforme l'IA de code en ressource accessible au profil fonctionnel via une interface de gestion de projet familière (inspirée de Jira).

---

## 3. Goals & Success Metrics

### 3.1 Goals V0

1. **Valider l'hypothèse produit centrale :** un PM non-tech tire-t-il plus de valeur d'un cadrage via notre UI dédiée que d'une conversation libre avec Claude/ChatGPT ?
2. **Prouver la faisabilité technique** du couple "chat conversationnel + structure adaptative + persistance" dans un MVP livrable rapidement
3. **Construire des fondations propres** sur lesquelles brancher les agents réels en V1 sans refonte majeure

### 3.2 Non-goals V0

- ❌ Exécution réelle de code par des agents
- ❌ Génération et exécution de tests
- ❌ Gestion de dépendances entre tâches
- ❌ Authentification ou multi-utilisateurs
- ❌ Intégrations externes (GitHub, Jira, Slack…)
- ❌ Déploiement cloud
- ❌ Multi-device / synchronisation
- ❌ Collaboration temps réel
- ❌ Accès au code produit

### 3.3 Success Metrics (testables)

| Métrique | Cible | Méthode de mesure |
|---|---|---|
| **Un projet complet peut être cadré de bout en bout** | 100% | Test fonctionnel manuel : entrer une idée, obtenir une arborescence validée |
| **Temps moyen pour cadrer un projet simple** | < 15 min | Mesure en session utilisateur |
| **Taux de validation des propositions de l'IA** | > 60% sans modification | Log des réponses PM lors du test |
| **Clarté ressentie du découpage** (feedback qualitatif) | Positif sur 2/3 testeurs | Debrief post-test avec 3 PMs réels |
| **L'outil est préféré à une conversation Claude libre** | 2/3 testeurs | Debrief post-test comparatif |

---

## 4. Target Users & Personas

### 4.1 Persona principal — "Claire, la PO solo"

- **Rôle :** Product Owner freelance / consultante produit / solopreneure
- **Expérience :** 3-8 ans en gestion de produit, très à l'aise avec Jira, Notion, Figma
- **Compétences techniques :** Aucune compétence en code. Connaît le vocabulaire (API, backend, frontend) sans savoir en produire.
- **Contexte d'usage :** Lance un nouveau projet perso ou client, seule, sans équipe dev
- **Motivations :**
  - Avoir **un outil unique** plutôt que jongler entre ChatGPT + Notion + feuille de route
  - Structurer ses idées avant de chercher de l'aide
  - Suivre l'avancement visuellement comme elle le faisait avec Jira
- **Frustrations actuelles :**
  - "Quand je discute avec Claude, mes réponses s'effacent, je n'ai pas de vue synthétique"
  - "Je ne sais jamais si j'ai pensé à tout dans mon découpage"
  - "Je n'ai personne à qui confier la réalisation"
- **Jobs-to-be-done :**
  1. *Quand j'ai une idée, je veux la structurer rapidement, pour sentir que je maîtrise le projet*
  2. *Quand je cadre une feature, je veux qu'on challenge mes angles morts, pour livrer quelque chose de solide*
  3. *Quand mon cadrage est prêt, je veux pouvoir le lancer en exécution, sans dépendre d'un dev*

### 4.2 Persona secondaire (V1) — "Marc, le solopreneur tech-curious"

- Dev junior ou tech-curious qui veut utiliser l'outil pour ses side-projects sans ouvrir son IDE

*Non-ciblé en V0.*

---

## 5. User Stories (haut niveau)

### Epic 1 — Gestion des projets

- **US-1.1** : En tant que PM, je veux voir la liste de mes projets sur l'écran d'accueil, afin de reprendre le travail rapidement
- **US-1.2** : En tant que PM, je veux créer un nouveau projet en quelques clics, afin de démarrer immédiatement
- **US-1.3** : En tant que PM, je veux supprimer un projet, afin de garder ma liste propre
- **US-1.4** : En tant que PM, je veux renommer un projet, afin de refléter son évolution

### Epic 2 — Cadrage conversationnel

- **US-2.1** : En tant que PM, je veux démarrer une conversation avec un agent de cadrage pour décrire mon idée en langage naturel
- **US-2.2** : En tant que PM, je veux que l'agent challenge mon idée avec des questions pertinentes, afin de détecter mes angles morts
- **US-2.3** : En tant que PM, je veux que l'agent évalue la complexité et propose un découpage adaptatif (Epic/US/Task)
- **US-2.4** : En tant que PM, je veux valider, rejeter ou ajuster la proposition de découpage **via le chat** uniquement
- **US-2.5** : En tant que PM, je veux que l'agent génère automatiquement les critères d'acceptance des User Stories
- **US-2.6** : En tant que PM, je veux ajouter de nouvelles demandes à un projet existant via le chat, afin de l'enrichir progressivement
- **US-2.7** : En tant que PM, je veux que l'historique de conversation soit persisté, afin de reprendre où j'en étais

### Epic 3 — Visualisation et navigation

- **US-3.1** : En tant que PM, je veux voir la liste plate de toutes les User Stories de mon projet
- **US-3.2** : En tant que PM, je veux voir la liste plate de toutes les Tasks de mon projet
- **US-3.3** : En tant que PM, je veux voir le détail d'un item (description, critères d'acceptance, statut, complexité)
- **US-3.4** : En tant que PM, je veux naviguer facilement entre les vues via des onglets
- **US-3.5** : En tant que PM, je veux que le chat reste visible en permanence sur la droite pour continuer à interagir pendant que je consulte

### Epic 4 — Suivi des statuts (avec agents mockés)

- **US-4.1** : En tant que PM, je veux voir le statut de chaque tâche (`To Do`, `In Progress`, `In Test`, `Done`)
- **US-4.2** : En tant que PM, je veux lancer l'exécution mockée d'une tâche pour voir le flow complet
- **US-4.3** : En tant que PM, je veux que les statuts s'actualisent automatiquement (mock)

---

## 6. Functional Requirements

### 6.1 Agent de cadrage conversationnel

**Rôle :** transformer une idée floue en arborescence projet structurée, via dialogue avec le PM.

**Comportements clés :**

- **FR-1.1 — Prise d'input initial** : accepte une description libre du projet/feature souhaité(e). Pas de format imposé.
- **FR-1.2 — Challenge proactif** : pose des questions de clarification ciblées sur les zones floues (ex : "Qui utilise cette feature ?", "Que se passe-t-il si X ?", "Veux-tu stocker ces données ?"). Vise 2-5 questions par itération.
- **FR-1.3 — Évaluation de complexité** : classifie chaque demande en `simple` / `medium` / `complex` selon des critères explicites :
  - `simple` → une tâche technique unique (ex : "ajouter un bouton")
  - `medium` → une User Story (ex : "permettre de filtrer les résultats")
  - `complex` → une Epic contenant plusieurs User Stories (ex : "système de paiement")
- **FR-1.4 — Découpage adaptatif** : génère automatiquement la bonne structure :
  - Complexité `simple` → Task seule (pas de parent)
  - Complexité `medium` → User Story avec critères d'acceptance
  - Complexité `complex` → Epic + N User Stories (chacune avec critères d'acceptance)
- **FR-1.5 — Génération des critères d'acceptance** : pour chaque US créée, l'agent propose automatiquement 3 à 7 critères d'acceptance au format Given/When/Then (ou liste simple si plus adapté). Le PM peut les valider, demander des ajustements, ou en ajouter via le chat.
- **FR-1.6 — Présentation de la proposition** : après découpage, l'agent renvoie un résumé textuel clair dans le chat (ex : "Voici la proposition : 1 Epic 'Paiement', 3 US, 12 critères d'acceptance au total. Détails visibles dans la liste US.").
- **FR-1.7 — Boucle de validation via chat uniquement** : le PM répond au bot par messages libres :
  - Validation explicite → les items passent en base avec statut `To Do`
  - Rejet / demande d'ajustement → l'agent régénère ou ajuste les items concernés
  - Zéro édition directe dans l'UI pour le V0
- **FR-1.8 — Enrichissement progressif** : le PM peut revenir plus tard et dire "ajoute une feature X", l'agent l'intègre dans le projet existant en respectant le même flow.
- **FR-1.9 — Persistance conversationnelle** : l'historique complet du chat est persisté par projet et rechargé à chaque ouverture.
- **FR-1.10 — Gestion des inputs flous** : si l'agent ne peut pas proposer un découpage pertinent (input trop vague), il demande des précisions plutôt que d'inventer.

**Personnalité du bot (défaut V0) :**
- Ton : professionnel, chaleureux, concis
- Style : pose UNE question à la fois pour ne pas saturer, ou maximum 3 questions groupées si elles sont étroitement liées
- Ne s'excuse pas, ne flatte pas, ne bullshit pas
- Propose des exemples concrets quand l'utilisateur bloque

### 6.2 Gestion des projets

- **FR-2.1 — Écran d'accueil (liste de projets)** : au lancement, l'app affiche une liste simple des projets existants
- **FR-2.2 — Création projet** : bouton "Nouveau projet" → saisie du nom → ouvre l'écran projet avec un chat vide prêt à recevoir l'idée
- **FR-2.3 — Sélection projet** : clic sur un projet de la liste → ouvre l'écran projet avec son arborescence et son historique chat
- **FR-2.4 — Suppression projet** : menu contextuel sur chaque projet → confirmation → suppression définitive (pas de corbeille)
- **FR-2.5 — Renommage projet** : édition inline du nom depuis la liste ou depuis l'écran projet

### 6.3 Visualisation et navigation

- **FR-3.1 — Layout écran projet** : chat fixe sur la droite (~1/3 de la largeur), zone principale au centre pour la navigation entre vues, header en haut avec nom du projet et navigation
- **FR-3.2 — Onglets de vue** : onglets (ou boutons) en haut de la zone centrale pour basculer entre :
  - **Liste des User Stories** (toutes les US du projet, toutes Epics confondues, triées par statut puis ordre de création)
  - **Liste des Tasks** (toutes les tâches techniques, toutes confondues)
  - *(Optionnel V0)* **Vue arborescente** : Epic → US → Task (si le dev est simple, sinon reporté)
- **FR-3.3 — Table de liste** : affichage tabulaire style Jira :
  - Colonnes : titre, type (Epic/US/Task), complexité, statut, parent (le cas échéant)
  - Statut affiché comme badge coloré
  - Clic sur une ligne → ouvre le panel de détail
- **FR-3.4 — Panel de détail d'item** : affiche le détail complet (titre, description, complexité, statut, critères d'acceptance, parent, enfants). Lecture seule en V0 (modifications via chat uniquement).
- **FR-3.5 — Persistance de la vue active** : l'onglet sélectionné est mémorisé entre les navigations dans la session courante

### 6.4 Suivi des statuts (mock V0)

- **FR-4.1 — Statuts supportés** : `To Do` → `In Progress` → `In Test` → `Done`
- **FR-4.2 — Affichage visuel** : chaque statut a une couleur distincte (inspiration Jira)
- **FR-4.3 — Bouton "Lancer l'exécution (mock)"** : sur chaque item en `To Do`, un bouton permet de lancer une simulation
- **FR-4.4 — Simulation temporisée** : après clic, l'item passe automatiquement `To Do` → `In Progress` (après 5s) → `In Test` (après 5s) → `Done` (après 5s)
- **FR-4.5 — Mise à jour temps réel (polling simple)** : le frontend interroge le backend toutes les 2s pour refléter les changements de statut
- **FR-4.6 — Architecture d'abstraction** : même en mock, la logique d'agents est encapsulée derrière une interface claire (`AgentExecutor`) pour faciliter le branchement d'agents réels en V1

### 6.5 Persistance

- **FR-5.1 — Base SQLite locale** : un seul fichier `ai_pm.db` à la racine du backend
- **FR-5.2 — Modèle de données** : défini en section 9
- **FR-5.3 — Sauvegarde automatique** : chaque action persistée immédiatement, pas de notion de "sauvegarde manuelle"
- **FR-5.4 — Pas d'import/export** en V0

---

## 7. Non-Functional Requirements

| Catégorie | Exigence |
|---|---|
| **Performance** | Réponse de l'agent LLM < 10s par tour ; navigation UI < 200ms |
| **Simplicité** | Lancement en 2 commandes max (`uvicorn` + `npm run dev`) |
| **Local-first** | Aucun cloud, aucune auth, aucune télémétrie |
| **Fiabilité** | Si l'API Claude échoue, message d'erreur clair dans le chat, pas de crash |
| **Reprise** | Redémarrer l'app → retrouver ses projets et conversations intactes |
| **Observabilité** | Logs backend simples (stdout) avec niveaux INFO/ERROR |
| **Browser support** | Chrome / Firefox / Edge dernières versions (pas d'IE, pas de mobile) |
| **Accessibilité** | Contrastes lisibles, focus visible, tab-navigation basique (pas d'a11y AAA) |

---

## 8. UX & Design Guidelines

### 8.1 Principes directeurs

- **"Simple comme Jira, en plus léger"** — réutiliser les codes visuels familiers (tables, badges, onglets)
- **Aucune fioriture** — pas d'animations superflues, pas de thèmes, pas de dark mode en V0
- **Chat omniprésent** — le chat est le cœur, il est **toujours visible** (côté droit fixe)
- **Lecture > édition** — en V0 tout ce qui est centre = affichage pur, pas de formulaires

### 8.2 Layout type (écran projet)

```
┌──────────────────────────────────────────────────────────────────┐
│  [Logo] Mon Projet Alpha                       [Projets] [⚙]    │ ← Header
├──────────────────────────────────────────────┬───────────────────┤
│  [User Stories] [Tasks] [Arborescence]       │                   │
│  ─────────────────────────────────────       │   💬 Chat         │
│                                              │                   │
│  Titre         | Type | Compl. | Statut      │   > Message 1     │
│  ───────────────────────────────────────     │   > Message 2     │
│  Ajout login   | US   | medium | To Do       │   > ...           │
│  Créer button  | Task | simple | In Progress │                   │
│  Paiement      | Epic | complex| —           │                   │
│  ...                                         │                   │
│                                              │   ┌─────────────┐ │
│                                              │   │ Votre msg...│ │
│                                              │   └─────────────┘ │
└──────────────────────────────────────────────┴───────────────────┘
```

### 8.3 Écrans à produire

| # | Écran | Contenu |
|---|---|---|
| 1 | **Accueil — Liste des projets** | Liste simple, bouton "Nouveau projet" |
| 2 | **Projet vide (fraîchement créé)** | Layout avec chat ouvert à droite, zone centrale vide avec message d'invite |
| 3 | **Projet actif — Vue User Stories** | Layout avec liste tabulaire au centre + chat |
| 4 | **Projet actif — Vue Tasks** | Idem mais table filtrée |
| 5 | **Panel de détail d'item** | Overlay ou side-panel affichant tous les détails |

### 8.4 Palette de statuts (inspiration Jira)

| Statut | Couleur indicative |
|---|---|
| `To Do` | Gris (`#DFE1E6`) |
| `In Progress` | Bleu (`#0052CC`) |
| `In Test` | Jaune (`#FFAB00`) |
| `Done` | Vert (`#36B37E`) |

---

## 9. Data Model

### 9.1 Entités principales

```
Project
  - id (UUID)
  - name (string, required)
  - description (text, nullable)
  - created_at (datetime)
  - updated_at (datetime)

Item (modèle unifié Epic/UserStory/Task)
  - id (UUID)
  - project_id (FK → Project)
  - parent_id (FK → Item, nullable) — pour hiérarchie Epic→US
  - type (enum: 'epic' | 'user_story' | 'task')
  - title (string, required)
  - description (text)
  - complexity (enum: 'simple' | 'medium' | 'complex')
  - status (enum: 'todo' | 'in_progress' | 'in_test' | 'done')
  - acceptance_criteria (JSON array of strings, nullable)
  - order (integer, pour le tri)
  - created_at, updated_at

ChatMessage
  - id (UUID)
  - project_id (FK → Project)
  - role (enum: 'user' | 'assistant' | 'system')
  - content (text)
  - metadata (JSON, nullable) — pour stocker les items proposés, etc.
  - created_at
```

### 9.2 Règles métier

- Un **Task** peut être enfant d'une User Story **ou** racine (tâche technique indépendante)
- Une **User Story** peut être enfant d'une Epic **ou** racine (US indépendante)
- Une **Epic** est toujours racine (pas d'Epic dans Epic en V0)
- `acceptance_criteria` n'est renseigné que pour les `user_story` (optionnellement pour `task` complexes)
- `status` : tous les types d'items suivent le même workflow de statuts
- La suppression d'un Project cascade sur tous ses Items et ChatMessages

---

## 10. Architecture Technique

### 10.1 Stack validée

| Couche | Technologie | Justification |
|---|---|---|
| **Backend** | Python 3.11+ + FastAPI | Décidé |
| **ORM** | SQLAlchemy 2.x | Décidé |
| **Base de données** | SQLite (fichier local) | Décidé |
| **Migrations** | Alembic | Standard avec SQLAlchemy |
| **LLM** | API Anthropic Claude (SDK officiel `anthropic`) | Qualité conversationnelle |
| **Frontend** | React 18+ (projet séparé) | Décidé |
| **Build front** | Vite | Le plus simple et rapide |
| **State management** | React Query + Zustand (ou Context) | Léger, pas de Redux |
| **UI library** | TailwindCSS + shadcn/ui (optionnel) | Look propre rapidement |
| **HTTP client front** | Fetch natif ou Axios | Au choix du dev front |
| **Packaging / run** | `uvicorn` (back) + `npm run dev` (front) | Zéro Docker en V0 |

### 10.2 Structure des projets

```
ai_project_manager/
├── backend/                    # Projet Python FastAPI
│   ├── app/
│   │   ├── main.py            # Entrée FastAPI
│   │   ├── config.py          # Config (clé API Claude, etc.)
│   │   ├── database.py        # Setup SQLAlchemy + SQLite
│   │   ├── models/            # Modèles SQLAlchemy
│   │   │   ├── project.py
│   │   │   ├── item.py
│   │   │   └── chat_message.py
│   │   ├── schemas/           # Schémas Pydantic (request/response)
│   │   ├── routers/           # Endpoints FastAPI
│   │   │   ├── projects.py
│   │   │   ├── items.py
│   │   │   └── chat.py
│   │   ├── services/          # Logique métier
│   │   │   ├── scoping_agent.py      # Agent de cadrage (appels Claude)
│   │   │   ├── agent_executor.py     # Interface abstraite pour V1
│   │   │   └── mock_executor.py      # Implémentation mock V0
│   │   └── utils/
│   ├── alembic/               # Migrations
│   ├── tests/
│   ├── pyproject.toml
│   └── .env.example
│
└── frontend/                   # Projet React séparé
    ├── src/
    │   ├── main.tsx
    │   ├── App.tsx
    │   ├── pages/
    │   │   ├── ProjectList.tsx
    │   │   └── ProjectView.tsx
    │   ├── components/
    │   │   ├── Chat/
    │   │   ├── ItemTable/
    │   │   ├── ItemDetail/
    │   │   └── StatusBadge.tsx
    │   ├── api/               # Client HTTP vers FastAPI
    │   ├── hooks/
    │   └── types/
    ├── package.json
    ├── vite.config.ts
    └── tailwind.config.js
```

### 10.3 API REST (endpoints principaux)

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects` | Liste tous les projets |
| `POST` | `/api/projects` | Crée un projet |
| `GET` | `/api/projects/{id}` | Détail d'un projet |
| `PATCH` | `/api/projects/{id}` | Renomme un projet |
| `DELETE` | `/api/projects/{id}` | Supprime un projet |
| `GET` | `/api/projects/{id}/items` | Liste les items (filtrable par type) |
| `GET` | `/api/items/{id}` | Détail d'un item |
| `POST` | `/api/items/{id}/execute` | Lance l'exécution mockée |
| `GET` | `/api/projects/{id}/messages` | Historique du chat |
| `POST` | `/api/projects/{id}/messages` | Envoie un message → réponse agent + items créés/modifiés |

### 10.4 Flow du chat (séquence)

```
1. User saisit un message dans le chat (frontend)
2. POST /api/projects/{id}/messages { content: "..." }
3. Backend persiste le message user
4. Backend charge l'historique complet de la conversation + état actuel des items
5. Backend construit le prompt système (rôle de l'agent de cadrage)
6. Backend appelle l'API Claude (streaming ou non)
7. Backend parse la réponse :
   - Texte pour le chat
   - (Optionnel) items proposés au format structuré (ex: JSON en fin de réponse ou via tool-use)
8. Backend persiste le message assistant + crée/modifie les items si applicable
9. Backend renvoie au frontend : { message, updated_items }
10. Frontend affiche la réponse + rafraîchit les listes
```

### 10.5 Interface `AgentExecutor` (pour V1-ready)

```python
# services/agent_executor.py
from abc import ABC, abstractmethod

class AgentExecutor(ABC):
    @abstractmethod
    async def aexecute_item(self, item_id: str) -> None:
        """Lance l'exécution d'un item et fait évoluer son statut."""
        pass

# services/mock_executor.py
class MockExecutor(AgentExecutor):
    async def aexecute_item(self, item_id: str) -> None:
        # Transitions temporisées: To Do → In Progress → In Test → Done
        ...
```

En V1, il suffira de créer un `ClaudeCodeExecutor(AgentExecutor)` sans toucher au reste.

---

## 11. Prompt Design (Agent de cadrage)

Le prompt système est le **cœur de valeur** du V0. Voici les principes directeurs (le prompt exact sera itéré) :

### 11.1 Rôle de l'agent

> *"Tu es un Product Coach expérimenté qui aide des Product Managers non-techniciens à transformer leurs idées en projets structurés. Ton rôle est d'écouter, challenger avec bienveillance, clarifier les angles morts, puis proposer un découpage pragmatique."*

### 11.2 Règles de comportement

- Pose **une seule question à la fois** (ou max 3 si étroitement liées)
- **Évalue la complexité** explicitement avant de proposer un découpage
- Propose une **structure adaptée** : Task seule / US seule / Epic + US
- **Génère des critères d'acceptance** automatiquement pour chaque US
- **Ne bullshit pas** — si tu ne comprends pas, demande
- **Ne surdécompose pas** — si c'est une petite feature, reste une Task
- **Reste concis** — le PM n'a pas de temps pour des monologues

### 11.3 Format de sortie structuré

La réponse de l'agent contient :
1. **Un message texte** pour le chat (explication, questions, résumé)
2. **Un bloc structuré** (JSON ou tool-use Claude) décrivant les items à créer/modifier :

```json
{
  "action": "propose_items" | "ask_question" | "confirm",
  "items": [
    {
      "type": "epic" | "user_story" | "task",
      "title": "...",
      "description": "...",
      "complexity": "simple" | "medium" | "complex",
      "parent_ref": null | "temp_id_xxx",
      "acceptance_criteria": ["...", "..."]
    }
  ]
}
```

Le backend interprète ce bloc et crée les items en base.

---

## 12. V0 Scope Summary — Acceptance Criteria

Le V0 est considéré comme **livré** quand :

- [ ] Un utilisateur peut créer un nouveau projet depuis l'écran d'accueil
- [ ] Un utilisateur peut décrire une idée en langage naturel dans le chat
- [ ] L'agent challenge l'idée avec des questions pertinentes
- [ ] L'agent propose un découpage adaptatif (simple → Task, medium → US, complex → Epic + US)
- [ ] L'agent génère les critères d'acceptance pour les User Stories
- [ ] Le PM peut valider ou rejeter les propositions via le chat uniquement
- [ ] Les items validés apparaissent dans la liste correspondante (US ou Tasks)
- [ ] Le PM peut voir le détail d'un item en cliquant dessus
- [ ] Le PM peut lancer l'exécution mockée d'un item et voir les statuts évoluer
- [ ] Les projets, items et conversations sont persistés entre les redémarrages
- [ ] L'UI est stable et navigable sans bug bloquant sur Chrome
- [ ] Le projet peut être lancé en 2 commandes (`uvicorn` + `npm run dev`) sur une machine vierge

---

## 13. Risks & Open Questions

### 13.1 Risques

| # | Risque | Criticité | Mitigation |
|---|---|---|---|
| R1 | Syndrome "Jira avec IA" — recréer Jira sans valeur différenciante | 🔴 Haute | Rester radical sur la simplicité et les non-goals ; tester tôt avec de vrais PMs |
| R2 | Qualité du cadrage IA insuffisante | 🟠 Moyenne | Prompt engineering itératif, test continu sur des idées variées |
| R3 | Format structuré instable (JSON malformé par le LLM) | 🟠 Moyenne | Utiliser le **tool-use** de Claude (plus fiable que du JSON free-form) |
| R4 | UX du "tout par chat" frustrante pour des modifications fines | 🟡 Moyenne | Accepter la friction en V0, prévoir l'édition directe en V1 si confirmé |
| R5 | Coût API Claude | 🟢 Faible | Usage solo = quelques euros/mois max |
| R6 | Mock d'agents qui cache des problèmes d'architecture V1 | 🟡 Moyenne | Interface `AgentExecutor` abstraite dès V0 |

### 13.2 Questions ouvertes (à trancher pendant le dev)

- Doit-on utiliser **Claude tool-use** (function calling) ou un JSON parsing à la main dans les réponses ?
- Faut-il un **streaming** des réponses LLM dans le chat ou un affichage à la fin de la réponse ? (Streaming est meilleur UX mais plus complexe)
- Faut-il une **vue arborescente** en plus des vues listes dès le V0, ou la reporter au V0.1 ?
- Quelle **clé API Claude** est utilisée : variable d'environnement ? Saisie dans l'UI ? (Reco : `.env` pour V0)

---

## 14. Out of Scope (rappel)

Pour éviter toute ambiguïté, **NE sont PAS inclus** dans le V0 :

- ❌ Authentification, multi-users, permissions
- ❌ Agents de dev/QA réels (mockés uniquement)
- ❌ Gestion des dépendances entre tâches
- ❌ Exécution asynchrone avec queue
- ❌ Vue Kanban / Gantt / Burndown
- ❌ Édition directe des items (tout passe par le chat)
- ❌ Import/export de projets
- ❌ Intégrations GitHub / Jira / Linear / Slack
- ❌ Déploiement cloud / Docker / CI/CD
- ❌ Tests automatisés du code produit
- ❌ Gestion des pièces jointes, images, fichiers
- ❌ Notifications, rappels, collaboration
- ❌ Historique / audit trail / versioning
- ❌ Thèmes, dark mode, personnalisation
- ❌ i18n (français uniquement en V0)
- ❌ Mobile / responsive (desktop Chrome uniquement)

---

## 15. Next Steps

1. **Valider ce PRD** avec Etienne
2. **Session dédiée au prompt design** de l'agent de cadrage (critique pour la valeur V0)
3. **Wireframes rapides** des 5 écrans clés
4. **Découpage Epics/Stories** détaillé (à faire avec le PM agent : menu `[CE]`)
5. **Setup technique** : initialiser les deux projets (backend FastAPI + frontend React)
6. **Walking skeleton** : chat basique qui répond + liste vide qui s'affiche (objectif 1-2 jours)
7. **Itérations fonctionnelles** par tranches verticales
8. **Test utilisateur précoce** avec 1-2 PMs réels dès que le MVP est navigable

---

**Fin du PRD V0.**
