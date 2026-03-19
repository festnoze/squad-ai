# EduFlow Evolution - Document Technique d'Implémentation

## Optimisation Évolutive de Workflows d'Agents IA pour l'Éducation

**Version** : 1.0
**Date** : 2026-02-06
**Auteur** : Analyse technique générée par Claude Opus 4.6

---

## Table des Matières

1. [Stack Technique Recommandé](#1-stack-technique-recommandé)
2. [Implémentation des Opérateurs Génétiques](#2-implémentation-des-opérateurs-génétiques)
3. [Bootstrap et Séquence de Démarrage](#3-bootstrap-et-séquence-de-démarrage)
4. [Architecture du Code](#4-architecture-du-code)
5. [Estimation des Coûts](#5-estimation-des-coûts)

---

## 1. Stack Technique Recommandé

### 1.1 Choix du Framework d'Orchestration Multi-Agents

#### Option A : Claude Agent SDK (Anthropic) - RECOMMANDÉ

Le **Claude Agent SDK** (anciennement Claude Code SDK) est le framework natif d'Anthropic pour construire des systèmes d'agents. Il offre un pattern supervisor + tools natif via le mécanisme de **subagents** et de **custom MCP tools**.

**Capacités clés pour EduFlow Evolution :**

- **Subagents natifs** : Le SDK supporte nativement les subagents qui tournent dans des contextes isolés et renvoient uniquement l'information pertinente à l'orchestrateur. C'est exactement le pattern supervisor + sub-agents comme tools.
- **Custom Tools via MCP in-process** : Les tools sont définis comme des serveurs MCP in-process (pas de subprocess), ce qui élimine le overhead IPC et simplifie le déploiement.
- **`AgentDefinition` programmatique** : On peut définir des subagents dynamiquement avec `system_prompt`, `tools`, et `model` -- ce qui permet de **matérialiser un génome en agent exécutable** à la volée.
- **Contrôle fin** : `ClaudeAgentOptions` expose `system_prompt`, `allowed_tools`, `model`, `max_turns`, `max_budget_usd`, `hooks` -- tous les leviers nécessaires pour paramétrer dynamiquement un workflow depuis un génome.
- **Hooks** : `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStop` permettent d'instrumenter la télémétrie (M1) sans modifier les agents.

**Exemple de matérialisation d'un génome en agent exécutable :**

```python
from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions, AgentDefinition,
    tool, create_sdk_mcp_server, AssistantMessage, TextBlock, ResultMessage
)
from typing import Any
import asyncio

async def amaterialize_workflow(genome: dict) -> ClaudeAgentOptions:
    """Transforme un génome JSON en configuration d'agent exécutable."""

    # Créer les tools MCP à partir du génome
    custom_tools = []
    for tool_def in genome.get("tools", []):
        @tool(tool_def["name"], tool_def["description"], tool_def["schema"])
        async def tool_handler(args: dict[str, Any], _def=tool_def) -> dict[str, Any]:
            # Chaque tool peut être un wrapper vers un sub-agent spécialisé
            return {"content": [{"type": "text", "text": f"Résultat de {_def['name']}"}]}
        custom_tools.append(tool_handler)

    mcp_server = create_sdk_mcp_server(
        name="workflow-tools",
        version="1.0.0",
        tools=custom_tools
    )

    # Créer les subagents depuis le génome
    agents = {}
    for agent_def in genome.get("agents", []):
        agents[agent_def["id"]] = AgentDefinition(
            description=agent_def["description"],
            prompt=agent_def["system_prompt"],
            tools=agent_def.get("allowed_tools"),
            model=agent_def.get("model", "haiku")  # "sonnet", "opus", "haiku", "inherit"
        )

    # Assembler le workflow
    allowed_tool_names = [
        f"mcp__workflow-tools__{t['name']}" for t in genome.get("tools", [])
    ]

    return ClaudeAgentOptions(
        system_prompt=genome["supervisor"]["system_prompt"],
        mcp_servers={"workflow-tools": mcp_server},
        allowed_tools=allowed_tool_names,
        agents=agents,
        model=genome["supervisor"].get("model", "claude-sonnet-4"),
        max_turns=genome.get("max_turns", 15),
        max_budget_usd=genome.get("max_budget_usd", 0.50),
        permission_mode="bypassPermissions"
    )


async def aevaluate_individual(genome: dict, query: str) -> dict:
    """Exécute un workflow (individu) sur une query et collecte la télémétrie."""
    options = await amaterialize_workflow(genome)

    response_text = ""
    telemetry = {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "duration_ms": 0}

    async with ClaudeSDKClient(options=options) as client:
        await client.query(query)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text
            elif isinstance(message, ResultMessage):
                telemetry["duration_ms"] = message.duration_ms
                telemetry["cost_usd"] = message.total_cost_usd or 0.0
                if message.usage:
                    telemetry["tokens_in"] = message.usage.get("input_tokens", 0)
                    telemetry["tokens_out"] = message.usage.get("output_tokens", 0)

    return {"response": response_text, "telemetry": telemetry}
```

**Limitations du Claude Agent SDK pour ce projet :**

- Verrouillé sur l'écosystème Anthropic (pas de modèles OpenAI/Mistral)
- Le SDK lance un CLI sous-jacent -- chaque `query()` est un processus
- Pas de contrôle direct sur la `temperature` dans `ClaudeAgentOptions` (il faut passer par `extra_args` ou l'API directe)
- Le parallélisme massif (100 individus simultanés) nécessite une gestion fine des processus

#### Option B : LangGraph

LangGraph est le standard industriel 2026 pour l'orchestration multi-agents avec state management.

**Avantages :**
- Graphes d'exécution explicites (parfait pour modéliser la hiérarchie du workflow)
- State management natif (facilite la télémétrie M1)
- Support multi-modèles (Claude, GPT, Mistral, modèles locaux)
- Contrôle total sur `temperature`, `max_tokens`, et tous les paramètres LLM
- Checkpointing natif pour la reprise après erreur
- Parallélisme natif via les branches du graphe

**Inconvénients :**
- Verbosité : plus de boilerplate que le Claude Agent SDK
- Courbe d'apprentissage plus raide
- Pas de "sub-agents as tools" natif -- il faut l'implémenter manuellement

#### Option C : CrewAI

**Non recommandé pour ce projet.** CrewAI est orienté rôles statiques et ne supporte pas bien la dynamique de workflows générés programmatiquement depuis des génomes variables. Le pattern "role-based" est trop rigide pour l'évolution génétique de structures d'agents.

#### Option D : AutoGen (Microsoft)

**Partiellement adapté.** AutoGen excelle dans les conversations entre agents mais manque de contrôle fin sur la structure du workflow. La topologie conversationnelle est difficile à encoder dans un génome.

#### Recommandation Finale : Architecture Hybride

```
+--------------------------------------------------+
|          COUCHE ÉVOLUTION (Python pur)            |
|  Algorithme génétique, sélection, crossover,      |
|  mutation, gestion des populations                 |
+--------------------------------------------------+
                       |
                       | Génome JSON
                       v
+--------------------------------------------------+
|        COUCHE EXÉCUTION (Claude Agent SDK)        |
|  Matérialisation du génome -> ClaudeAgentOptions   |
|  Exécution via ClaudeSDKClient                     |
|  Collecte télémétrie via ResultMessage             |
+--------------------------------------------------+
                       |
                       | Fallback pour évaluations en masse
                       v
+--------------------------------------------------+
|    COUCHE ÉVALUATION (API Anthropic directe)      |
|  anthropic.AsyncAnthropic() pour éval batch       |
|  Batch API pour réductions de 50%                  |
|  Contrôle fin temperature, structured output       |
+--------------------------------------------------+
```

**Justification :**
- Le **Claude Agent SDK** pour l'exécution des workflows (pattern supervisor natif, subagents, hooks pour télémétrie)
- L'**API Anthropic directe** (`anthropic` Python SDK) pour les évaluations en masse (Batch API -50%, contrôle `temperature`, structured output JSON)
- Le **code Python pur** pour l'algorithme génétique (pas besoin de framework -- c'est du calcul sur des structures de données)

### 1.2 Recommandation de Modèles LLM

Basé sur la tarification officielle Anthropic de février 2026 :

| Modèle | Input/MTok | Output/MTok | Batch Input | Batch Output | Rôle recommandé |
|--------|-----------|-------------|-------------|--------------|-----------------|
| **Haiku 4.5** | $1.00 | $5.00 | $0.50 | $2.50 | Éval micro (M6 critères simples), agents légers |
| **Sonnet 4.5** | $3.00 | $15.00 | $1.50 | $7.50 | Supervisor, agents principaux, éval macro |
| **Opus 4.6** | $5.00 | $25.00 | $2.50 | $12.50 | Éval finale, arbitrage, ground truth validation |

**Stratégie de modèles mixtes recommandée :**

| Composant | Modèle | Justification |
|-----------|--------|---------------|
| **Exécution des workflows (Pop. A)** | Sonnet 4.5 (supervisor) + Haiku 4.5 (sub-agents) | Équilibre qualité/coût pour les agents pédagogiques |
| **Évaluation micro (Pop. B)** | Haiku 4.5 via Batch API | 12 critères simples (grammaire, longueur, format) -- Haiku suffit |
| **Évaluation méso (Pop. B)** | Sonnet 4.5 via Batch API | 5 critères complexes (cohérence, pertinence, pédagogie) |
| **Évaluation macro (Pop. B)** | Sonnet 4.5 | 2 critères holistiques (qualité globale, comparaison) |
| **Génération adversariale (Pop. C)** | Sonnet 4.5 | Créativité nécessaire pour les challenges |
| **Validation ground truth (Couche 0)** | Opus 4.6 (1x par génération) | Calibration haute fidélité |

**Optimisation via Prompt Caching :**

Le caching est critique car les system prompts des évaluateurs sont réutilisés massivement :
- Cache write (5min) : 1.25x le prix input
- **Cache read : 0.1x le prix input** (90% de réduction !)
- Sur 50 évaluations avec le même system prompt évaluateur, seule la 1ère paie le prix plein

### 1.3 Stockage

| Donnée | Volume estimé | Solution recommandée | Justification |
|--------|---------------|---------------------|---------------|
| **Génomes** (générations) | ~500 Ko/génération x 200 gén. = ~100 Mo | **SQLite** + JSON | Simple, embarqué, requêtes SQL pour l'analyse |
| **Jurisprudence** (M3) | ~50 Mo après 200 gén. | **SQLite** (table dédiée) | Index sur fitness, query, génération |
| **Télémétrie** (M1) | ~200 Mo après 200 gén. | **SQLite** (table dédiée) | Séries temporelles, agrégations |
| **Ground Truth** (Couche 0) | ~50 paires = ~50 Ko | **YAML** versionné Git | Immuable, revue humaine, diff-friendly |
| **Réponses brutes** | ~2 Go après 200 gén. | **Fichiers JSON** sur disque | Trop volumineux pour SQLite, accès séquentiel |
| **Logs d'évolution** | ~500 Mo | **Fichiers JSONL** | Append-only, streaming, analyse post-hoc |

**Schéma SQLite principal :**

```sql
CREATE TABLE generations (
    id INTEGER PRIMARY KEY,
    generation_num INTEGER NOT NULL,
    phase TEXT NOT NULL,  -- 'exploration' ou 'optimization'
    timestamp TEXT NOT NULL,
    config JSON NOT NULL,  -- paramètres GA de cette génération
    stats JSON NOT NULL    -- fitness min/max/avg, diversité, etc.
);

CREATE TABLE individuals (
    id TEXT PRIMARY KEY,  -- UUID
    generation_id INTEGER REFERENCES generations(id),
    population TEXT NOT NULL,  -- 'workflow', 'evaluator', 'adversarial'
    genome JSON NOT NULL,
    fitness_vector JSON,  -- vecteur 19D pour Pop. A
    fitness_scalar REAL,  -- fitness agrégée
    parent_ids JSON,  -- [parent1_id, parent2_id] ou [parent_id] pour mutation
    operator TEXT,  -- 'crossover', 'mutation_prompt', 'mutation_structure', etc.
    is_elite BOOLEAN DEFAULT FALSE,
    metadata JSON
);

CREATE TABLE evaluations (
    id INTEGER PRIMARY KEY,
    individual_id TEXT REFERENCES individuals(id),
    evaluator_id TEXT REFERENCES individuals(id),
    query_id TEXT REFERENCES individuals(id),
    scores JSON NOT NULL,  -- {critère: score} pour les 19 critères
    reasoning TEXT,  -- explication de l'évaluateur
    timestamp TEXT NOT NULL,
    cost_usd REAL,
    tokens_used INTEGER
);

CREATE TABLE telemetry (
    id INTEGER PRIMARY KEY,
    individual_id TEXT REFERENCES individuals(id),
    query TEXT NOT NULL,
    response TEXT NOT NULL,
    duration_ms INTEGER,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd REAL,
    tool_calls JSON,  -- [{tool_name, args, result, duration_ms}]
    error TEXT
);

CREATE INDEX idx_individuals_generation ON individuals(generation_id);
CREATE INDEX idx_individuals_fitness ON individuals(fitness_scalar DESC);
CREATE INDEX idx_evaluations_individual ON evaluations(individual_id);
CREATE INDEX idx_telemetry_individual ON telemetry(individual_id);
```

### 1.4 Parallélisme

L'architecture de parallélisme est cruciale car chaque génération implique potentiellement :
- 50 individus x 50 queries = 2 500 exécutions de workflow
- 2 500 x 19 critères = 47 500 évaluations

**Architecture de parallélisme recommandée :**

```python
import asyncio
from asyncio import Semaphore
from dataclasses import dataclass

@dataclass
class ParallelismConfig:
    """Configuration du parallélisme adaptatif."""
    max_concurrent_workflows: int = 10      # Limité par les processus Claude CLI
    max_concurrent_evaluations: int = 50    # API directe, plus léger
    max_concurrent_batch_requests: int = 5  # Batch API Anthropic
    rate_limit_rpm: int = 4000              # Requests per minute (Tier 3)
    rate_limit_tpm: int = 400_000           # Tokens per minute (Tier 3)

class AsyncExecutionEngine:
    """Moteur d'exécution parallèle avec rate limiting."""

    def __init__(self, config: ParallelismConfig):
        self.config = config
        self._workflow_sem = Semaphore(config.max_concurrent_workflows)
        self._eval_sem = Semaphore(config.max_concurrent_evaluations)
        self._rate_limiter = TokenBucketRateLimiter(
            rpm=config.rate_limit_rpm,
            tpm=config.rate_limit_tpm
        )

    async def aexecute_generation(
        self,
        workflows: list[dict],
        queries: list[str],
        evaluators: list[dict]
    ) -> list[dict]:
        """Exécute une génération complète avec parallélisme contrôlé."""

        # Phase 1 : Exécution des workflows (I/O bound, processus externes)
        execution_results = await self._arun_workflows_parallel(workflows, queries)

        # Phase 2 : Évaluation en batch (API calls, hautement parallélisable)
        evaluation_results = await self._aevaluate_batch(
            execution_results, evaluators
        )

        return evaluation_results

    async def _arun_workflows_parallel(
        self, workflows: list[dict], queries: list[str]
    ) -> list[dict]:
        """Exécute les workflows avec sémaphore de concurrence."""
        tasks = []
        for workflow in workflows:
            for query in queries:
                tasks.append(
                    self._arun_single_workflow(workflow, query)
                )
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def _arun_single_workflow(self, workflow: dict, query: str) -> dict:
        async with self._workflow_sem:
            await self._rate_limiter.aacquire()
            return await aevaluate_individual(workflow, query)

    async def _aevaluate_batch(
        self, results: list[dict], evaluators: list[dict]
    ) -> list[dict]:
        """Utilise la Batch API Anthropic pour les évaluations (-50% coût)."""
        import anthropic

        client = anthropic.AsyncAnthropic()

        # Préparer les requêtes batch
        batch_requests = []
        for i, (result, evaluator) in enumerate(
            self._generate_eval_pairs(results, evaluators)
        ):
            batch_requests.append({
                "custom_id": f"eval-{i}",
                "params": {
                    "model": evaluator.get("model", "claude-haiku-4-5"),
                    "max_tokens": 1024,
                    "system": evaluator["system_prompt"],
                    "messages": [{
                        "role": "user",
                        "content": self._format_eval_prompt(result, evaluator)
                    }]
                }
            })

        # Soumettre le batch (50% de réduction automatique)
        batch = await client.messages.batches.create(requests=batch_requests)

        # Attendre le résultat (la Batch API est asynchrone)
        while batch.processing_status != "ended":
            await asyncio.sleep(30)
            batch = await client.messages.batches.retrieve(batch.id)

        # Récupérer les résultats
        results = []
        async for result in client.messages.batches.results(batch.id):
            results.append(result)

        return results
```

**Stratégie de parallélisme par phase :**

| Phase | Méthode | Concurrence | Justification |
|-------|---------|-------------|---------------|
| Exécution workflows | `asyncio` + Semaphore(10) | 10 simultanés | Chaque workflow = 1 processus CLI |
| Évaluation micro | Batch API Anthropic | 50K requêtes/batch | -50% coût, latence acceptable (< 24h) |
| Évaluation méso/macro | `asyncio` + Semaphore(50) | 50 simultanés | Temps réel nécessaire pour le feedback |
| Opérateurs génétiques | `multiprocessing.Pool` | N CPU cores | CPU-bound (manipulations de génomes) |
| Sérialisation/IO | `aiofiles` + `aiosqlite` | Async natif | Non-bloquant |

---

## 2. Implémentation des Opérateurs Génétiques

### 2.1 Représentation du Génome

Le génome encode l'intégralité d'un workflow d'agents. Voici la structure JSON complète :

```python
from dataclasses import dataclass, field
from typing import Optional
import json
import uuid

@dataclass
class ToolGene:
    """Gène représentant un tool disponible pour un agent."""
    name: str
    description: str  # "Tool card" -- description visible par le LLM
    schema: dict      # JSON Schema des paramètres
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "schema": self.schema,
            "enabled": self.enabled
        }

@dataclass
class AgentGene:
    """Gène représentant un agent (supervisor ou sub-agent)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    role: str = ""                    # 'supervisor', 'researcher', 'explainer', etc.
    system_prompt: str = ""           # Le prompt système complet
    tool_ids: list[str] = field(default_factory=list)  # IDs des tools accessibles
    model: str = "haiku"              # 'haiku', 'sonnet', 'opus', 'inherit'
    temperature: float = 0.7
    max_tokens: int = 2048

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "system_prompt": self.system_prompt,
            "tool_ids": self.tool_ids,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }

@dataclass
class WorkflowGenome:
    """Génome complet d'un workflow d'agents pédagogiques."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Niveau MACRO : structure du workflow
    supervisor: AgentGene = field(default_factory=AgentGene)
    sub_agents: list[AgentGene] = field(default_factory=list)

    # Niveau MÉSO : tools partagés
    tools: list[ToolGene] = field(default_factory=list)

    # Niveau MICRO : paramètres globaux
    max_turns: int = 10
    delegation_strategy: str = "auto"  # 'auto', 'sequential', 'parallel'

    # Métadonnées évolutives
    generation: int = 0
    parent_ids: list[str] = field(default_factory=list)
    mutation_history: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "supervisor": self.supervisor.to_dict(),
            "sub_agents": [a.to_dict() for a in self.sub_agents],
            "tools": [t.to_dict() for t in self.tools],
            "max_turns": self.max_turns,
            "delegation_strategy": self.delegation_strategy,
            "generation": self.generation,
            "parent_ids": self.parent_ids,
            "mutation_history": self.mutation_history
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowGenome":
        genome = cls()
        genome.id = data.get("id", str(uuid.uuid4()))
        genome.supervisor = AgentGene(**{
            k: v for k, v in data["supervisor"].items()
        })
        genome.sub_agents = [AgentGene(**a) for a in data.get("sub_agents", [])]
        genome.tools = [ToolGene(**t) for t in data.get("tools", [])]
        genome.max_turns = data.get("max_turns", 10)
        genome.delegation_strategy = data.get("delegation_strategy", "auto")
        genome.generation = data.get("generation", 0)
        genome.parent_ids = data.get("parent_ids", [])
        genome.mutation_history = data.get("mutation_history", [])
        return genome

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
```

### 2.2 Crossover sur les Prompts (Niveau Micro)

Le crossover de prompts est inspiré des travaux de **EvoPrompt** (ICLR 2024) et **GAAPO** (Frontiers in AI, 2025). Contrairement aux algorithmes génétiques classiques qui opèrent sur des bits, ici on opère sur du texte en langage naturel qui doit rester **cohérent et sémantiquement valide**.

**Trois stratégies de crossover de prompts :**

```python
import random
import re
from anthropic import AsyncAnthropic

class PromptCrossover:
    """Opérateurs de crossover pour les system prompts."""

    def __init__(self, llm_client: AsyncAnthropic):
        self.client = llm_client

    # --- Stratégie 1 : Crossover par paragraphes ---

    def crossover_by_paragraphs(
        self, prompt_a: str, prompt_b: str, ratio: float = 0.5
    ) -> str:
        """Crossover structurel par blocs de paragraphes.

        Découpe les deux prompts en paragraphes et recombine.
        Simple, rapide, ne nécessite pas de LLM.
        """
        paras_a = [p.strip() for p in prompt_a.split("\n\n") if p.strip()]
        paras_b = [p.strip() for p in prompt_b.split("\n\n") if p.strip()]

        result = []
        max_len = max(len(paras_a), len(paras_b))

        for i in range(max_len):
            if random.random() < ratio:
                if i < len(paras_a):
                    result.append(paras_a[i])
            else:
                if i < len(paras_b):
                    result.append(paras_b[i])

        return "\n\n".join(result) if result else prompt_a

    # --- Stratégie 2 : Crossover par sections sémantiques ---

    def crossover_by_sections(
        self, prompt_a: str, prompt_b: str
    ) -> str:
        """Crossover intelligent par sections sémantiques.

        Identifie les sections (## Rôle, ## Instructions, ## Contraintes, etc.)
        et recombine section par section.
        """
        def _extract_sections(prompt: str) -> dict[str, str]:
            sections = {}
            current_key = "__header__"
            current_content = []

            for line in prompt.split("\n"):
                if re.match(r'^#{1,3}\s+', line):
                    sections[current_key] = "\n".join(current_content).strip()
                    current_key = line.strip()
                    current_content = []
                else:
                    current_content.append(line)

            sections[current_key] = "\n".join(current_content).strip()
            return {k: v for k, v in sections.items() if v}

        sections_a = _extract_sections(prompt_a)
        sections_b = _extract_sections(prompt_b)

        all_keys = list(dict.fromkeys(
            list(sections_a.keys()) + list(sections_b.keys())
        ))

        result_sections = []
        for key in all_keys:
            if key in sections_a and key in sections_b:
                chosen = sections_a[key] if random.random() < 0.5 else sections_b[key]
            elif key in sections_a:
                chosen = sections_a[key]
            else:
                chosen = sections_b[key]

            if key != "__header__":
                result_sections.append(f"{key}\n{chosen}")
            else:
                result_sections.insert(0, chosen)

        return "\n\n".join(result_sections)

    # --- Stratégie 3 : Crossover LLM-assisté (EvoPrompt-style) ---

    async def acrossover_llm_assisted(
        self, prompt_a: str, prompt_b: str, context: str = ""
    ) -> str:
        """Crossover assisté par LLM -- le LLM fusionne intelligemment.

        Inspiré de EvoPrompt (ICLR 2024). Le LLM agit comme opérateur
        de crossover en comprenant la sémantique des deux parents.
        Coûteux mais produit les résultats les plus cohérents.
        """
        meta_prompt = f"""Tu es un expert en ingénierie de prompts pour des agents IA pédagogiques.

Voici deux system prompts parents qui ont chacun des qualités différentes :

## Parent A (fitness: élevée sur la précision)
{prompt_a}

## Parent B (fitness: élevée sur la pédagogie)
{prompt_b}

{f"Contexte du cours : {context}" if context else ""}

Crée un NOUVEAU system prompt qui combine les meilleures qualités des deux parents.
Règles :
- Conserve les instructions les plus efficaces de chaque parent
- Élimine les redondances
- Assure la cohérence globale du prompt résultant
- Le résultat doit être un system prompt complet et opérationnel
- Conserve le même format (sections avec ##)

Réponds UNIQUEMENT avec le nouveau system prompt, sans explication."""

        response = await self.client.messages.create(
            model="claude-haiku-4-5",  # Haiku suffit pour cette tâche
            max_tokens=2048,
            temperature=0.8,
            messages=[{"role": "user", "content": meta_prompt}]
        )

        return response.content[0].text
```

### 2.3 Crossover sur la Structure (Niveau Méso)

```python
import copy

class StructuralCrossover:
    """Opérateurs de crossover sur la structure du workflow."""

    def crossover_swap_agents(
        self, genome_a: WorkflowGenome, genome_b: WorkflowGenome
    ) -> WorkflowGenome:
        """Échange des sub-agents entre deux workflows.

        Chaque sub-agent est échangé avec une probabilité de 50%.
        Les tools associés suivent l'agent.
        """
        child = copy.deepcopy(genome_a)
        child.id = str(uuid.uuid4())
        child.parent_ids = [genome_a.id, genome_b.id]

        # Collecter tous les agents des deux parents
        agents_a = {a.role: a for a in genome_a.sub_agents}
        agents_b = {a.role: a for a in genome_b.sub_agents}
        all_roles = set(agents_a.keys()) | set(agents_b.keys())

        child.sub_agents = []
        for role in all_roles:
            if role in agents_a and role in agents_b:
                # Le rôle existe dans les deux : choisir aléatoirement
                chosen = copy.deepcopy(
                    agents_a[role] if random.random() < 0.5 else agents_b[role]
                )
                child.sub_agents.append(chosen)
            elif role in agents_a:
                # Uniquement dans A : inclure avec probabilité 0.7
                if random.random() < 0.7:
                    child.sub_agents.append(copy.deepcopy(agents_a[role]))
            else:
                # Uniquement dans B : inclure avec probabilité 0.3
                if random.random() < 0.3:
                    child.sub_agents.append(copy.deepcopy(agents_b[role]))

        # Assurer que les tool_ids référencent des tools existants
        valid_tool_ids = {t.name for t in child.tools}
        for agent in child.sub_agents:
            agent.tool_ids = [tid for tid in agent.tool_ids if tid in valid_tool_ids]

        child.mutation_history.append("crossover_swap_agents")
        return child

    def crossover_swap_tools(
        self, genome_a: WorkflowGenome, genome_b: WorkflowGenome
    ) -> WorkflowGenome:
        """Échange des tools entre deux workflows.

        Les tools sont échangés individuellement. Les agents qui
        utilisaient un tool échangé voient leur liste mise à jour.
        """
        child = copy.deepcopy(genome_a)
        child.id = str(uuid.uuid4())
        child.parent_ids = [genome_a.id, genome_b.id]

        tools_a = {t.name: t for t in genome_a.tools}
        tools_b = {t.name: t for t in genome_b.tools}
        all_tool_names = set(tools_a.keys()) | set(tools_b.keys())

        child.tools = []
        for name in all_tool_names:
            if name in tools_a and name in tools_b:
                # Le tool existe dans les deux : prendre la meilleure description
                chosen = copy.deepcopy(
                    tools_a[name] if random.random() < 0.5 else tools_b[name]
                )
                child.tools.append(chosen)
            elif name in tools_a and random.random() < 0.6:
                child.tools.append(copy.deepcopy(tools_a[name]))
            elif name in tools_b and random.random() < 0.4:
                child.tools.append(copy.deepcopy(tools_b[name]))

        child.mutation_history.append("crossover_swap_tools")
        return child

    def crossover_supervisor_blend(
        self, genome_a: WorkflowGenome, genome_b: WorkflowGenome
    ) -> WorkflowGenome:
        """Crossover hybride : supervisor d'un parent, sub-agents de l'autre."""
        child = copy.deepcopy(genome_a)
        child.id = str(uuid.uuid4())
        child.parent_ids = [genome_a.id, genome_b.id]

        # Prendre le supervisor de A et les sub-agents de B (ou l'inverse)
        if random.random() < 0.5:
            child.supervisor = copy.deepcopy(genome_a.supervisor)
            child.sub_agents = copy.deepcopy(genome_b.sub_agents)
        else:
            child.supervisor = copy.deepcopy(genome_b.supervisor)
            child.sub_agents = copy.deepcopy(genome_a.sub_agents)

        # Fusionner les tools des deux parents
        all_tools = {t.name: t for t in genome_a.tools}
        all_tools.update({t.name: t for t in genome_b.tools})
        child.tools = list(all_tools.values())

        child.mutation_history.append("crossover_supervisor_blend")
        return child
```

### 2.4 Opérateurs de Mutation

```python
class MutationOperators:
    """Ensemble complet d'opérateurs de mutation multi-niveaux."""

    def __init__(self, llm_client: AsyncAnthropic):
        self.client = llm_client
        self.prompt_crossover = PromptCrossover(llm_client)

    # ===== MUTATIONS MICRO (prompts et paramètres) =====

    async def amutate_prompt_paraphrase(
        self, genome: WorkflowGenome, agent_idx: int = -1
    ) -> WorkflowGenome:
        """Mutation par paraphrase LLM d'un prompt.

        Le LLM reformule le prompt en conservant le sens mais
        en explorant des formulations alternatives.
        """
        child = copy.deepcopy(genome)
        child.id = str(uuid.uuid4())
        child.parent_ids = [genome.id]

        # Sélectionner l'agent à muter
        if agent_idx == -1:
            target = random.choice(
                [child.supervisor] + child.sub_agents
            )
        else:
            all_agents = [child.supervisor] + child.sub_agents
            target = all_agents[agent_idx]

        meta_prompt = f"""Reformule le system prompt suivant en conservant exactement le même sens et les mêmes instructions, mais avec des formulations différentes. Varie la structure des phrases, le vocabulaire (synonymes), et l'ordre des instructions secondaires.

System prompt original :
---
{target.system_prompt}
---

Réponds UNIQUEMENT avec le prompt reformulé, sans explication."""

        response = await self.client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2048,
            temperature=0.9,
            messages=[{"role": "user", "content": meta_prompt}]
        )
        target.system_prompt = response.content[0].text
        child.mutation_history.append("mutate_prompt_paraphrase")
        return child

    async def amutate_prompt_injection(
        self, genome: WorkflowGenome, instruction: str = ""
    ) -> WorkflowGenome:
        """Mutation par injection d'une nouvelle instruction dans un prompt.

        Ajoute une instruction spécifique (ex: "Utilise des analogies",
        "Structure ta réponse en bullet points", etc.)
        """
        child = copy.deepcopy(genome)
        child.id = str(uuid.uuid4())
        child.parent_ids = [genome.id]

        target = random.choice([child.supervisor] + child.sub_agents)

        # Instructions pédagogiques candidates
        candidate_instructions = [
            "Utilise des analogies concrètes du quotidien pour expliquer les concepts abstraits.",
            "Structure ta réponse avec des titres clairs et une progression logique.",
            "Commence par un résumé en 2 phrases avant de développer.",
            "Propose un exemple concret après chaque concept théorique.",
            "Termine par 3 questions de vérification de compréhension.",
            "Adapte le niveau de langage à un étudiant de licence.",
            "Utilise des métaphores visuelles pour faciliter la mémorisation.",
            "Fais des liens explicites avec les prérequis du cours.",
            "Inclus un avertissement sur les erreurs courantes liées à ce sujet.",
            "Propose une mnémotechnique quand c'est pertinent.",
        ]

        if not instruction:
            instruction = random.choice(candidate_instructions)

        # Injecter à une position aléatoire dans le prompt
        paragraphs = target.system_prompt.split("\n\n")
        insert_pos = random.randint(0, len(paragraphs))
        paragraphs.insert(insert_pos, instruction)
        target.system_prompt = "\n\n".join(paragraphs)

        child.mutation_history.append(f"mutate_prompt_injection:{instruction[:30]}")
        return child

    def mutate_parameters(self, genome: WorkflowGenome) -> WorkflowGenome:
        """Mutation des paramètres numériques (temperature, max_tokens, etc.)."""
        child = copy.deepcopy(genome)
        child.id = str(uuid.uuid4())
        child.parent_ids = [genome.id]

        target = random.choice([child.supervisor] + child.sub_agents)

        # Mutation de la température (±0.1, borné [0.0, 1.5])
        delta_temp = random.gauss(0, 0.1)
        target.temperature = max(0.0, min(1.5, target.temperature + delta_temp))

        # Mutation du max_tokens (±256, borné [512, 8192])
        delta_tokens = random.choice([-512, -256, 0, 256, 512])
        target.max_tokens = max(512, min(8192, target.max_tokens + delta_tokens))

        # Mutation du modèle (rare, probabilité 10%)
        if random.random() < 0.1:
            models = ["haiku", "sonnet", "opus"]
            current_idx = models.index(target.model) if target.model in models else 0
            # Tendance vers le modèle adjacent (pas de saut haiku->opus)
            if random.random() < 0.5 and current_idx > 0:
                target.model = models[current_idx - 1]
            elif current_idx < len(models) - 1:
                target.model = models[current_idx + 1]

        child.mutation_history.append("mutate_parameters")
        return child

    def mutate_tool_description(self, genome: WorkflowGenome) -> WorkflowGenome:
        """Mutation de la description d'un tool (tool card).

        La description du tool influence quand et comment le supervisor
        l'utilise. Modifier cette description change le comportement
        de délégation du workflow.
        """
        child = copy.deepcopy(genome)
        child.id = str(uuid.uuid4())
        child.parent_ids = [genome.id]

        if not child.tools:
            return child

        target_tool = random.choice(child.tools)

        # Mutations simples de description
        mutations = [
            lambda d: d + " Utilise cet outil en priorité pour ce type de question.",
            lambda d: d + " Cet outil est particulièrement efficace pour les explications détaillées.",
            lambda d: d.replace(".", ". Fournit des réponses structurées."),
            lambda d: "IMPORTANT: " + d,
            lambda d: d + " À utiliser quand la question nécessite une analyse approfondie.",
        ]

        target_tool.description = random.choice(mutations)(target_tool.description)
        child.mutation_history.append(f"mutate_tool_description:{target_tool.name}")
        return child

    # ===== MUTATIONS MÉSO (structure des agents) =====

    def mutate_add_agent(self, genome: WorkflowGenome) -> WorkflowGenome:
        """Ajoute un nouveau sub-agent au workflow."""
        child = copy.deepcopy(genome)
        child.id = str(uuid.uuid4())
        child.parent_ids = [genome.id]

        # Templates d'agents pédagogiques
        agent_templates = [
            AgentGene(
                role="simplifier",
                system_prompt="Tu es un expert en vulgarisation. Ton rôle est de reformuler des concepts complexes en langage simple et accessible. Utilise des analogies du quotidien.",
                model="haiku",
                temperature=0.7
            ),
            AgentGene(
                role="fact_checker",
                system_prompt="Tu vérifies la précision factuelle des réponses pédagogiques. Signale toute imprécision, erreur ou affirmation non étayée. Sois rigoureux.",
                model="sonnet",
                temperature=0.2
            ),
            AgentGene(
                role="example_generator",
                system_prompt="Tu génères des exemples concrets, des exercices pratiques et des cas d'application pour illustrer les concepts théoriques enseignés.",
                model="haiku",
                temperature=0.9
            ),
            AgentGene(
                role="synthesizer",
                system_prompt="Tu produis des synthèses claires et structurées. Tu identifies les points clés, les organises logiquement et les formules de manière mémorable.",
                model="haiku",
                temperature=0.5
            ),
            AgentGene(
                role="socratic_questioner",
                system_prompt="Tu poses des questions socratiques pour guider l'étudiant vers la compréhension. Tu ne donnes pas la réponse directement mais amènes l'étudiant à la découvrir.",
                model="sonnet",
                temperature=0.8
            ),
        ]

        # Filtrer les rôles déjà présents
        existing_roles = {a.role for a in child.sub_agents}
        available = [t for t in agent_templates if t.role not in existing_roles]

        if available:
            new_agent = copy.deepcopy(random.choice(available))
            new_agent.id = str(uuid.uuid4())[:8]
            # Assigner des tools existants aléatoirement
            if child.tools:
                n_tools = random.randint(1, len(child.tools))
                new_agent.tool_ids = [
                    t.name for t in random.sample(child.tools, n_tools)
                ]
            child.sub_agents.append(new_agent)

        child.mutation_history.append(f"mutate_add_agent:{new_agent.role if available else 'none'}")
        return child

    def mutate_remove_agent(self, genome: WorkflowGenome) -> WorkflowGenome:
        """Supprime un sub-agent du workflow (jamais le supervisor)."""
        child = copy.deepcopy(genome)
        child.id = str(uuid.uuid4())
        child.parent_ids = [genome.id]

        if len(child.sub_agents) > 1:  # Garder au moins 1 sub-agent
            removed = random.choice(child.sub_agents)
            child.sub_agents.remove(removed)
            child.mutation_history.append(f"mutate_remove_agent:{removed.role}")

        return child

    def mutate_rewire_tools(self, genome: WorkflowGenome) -> WorkflowGenome:
        """Réattribue les tools entre agents (change qui a accès à quoi)."""
        child = copy.deepcopy(genome)
        child.id = str(uuid.uuid4())
        child.parent_ids = [genome.id]

        if not child.tools or not child.sub_agents:
            return child

        target = random.choice(child.sub_agents)
        tool_names = [t.name for t in child.tools]

        action = random.choice(["add", "remove", "shuffle"])

        if action == "add" and tool_names:
            available = [t for t in tool_names if t not in target.tool_ids]
            if available:
                target.tool_ids.append(random.choice(available))
        elif action == "remove" and target.tool_ids:
            target.tool_ids.remove(random.choice(target.tool_ids))
        elif action == "shuffle":
            random.shuffle(target.tool_ids)
            n_keep = random.randint(1, max(1, len(target.tool_ids)))
            target.tool_ids = target.tool_ids[:n_keep]

        child.mutation_history.append(f"mutate_rewire_tools:{target.role}:{action}")
        return child

    # ===== MUTATIONS MACRO (workflow complet) =====

    def mutate_delegation_strategy(self, genome: WorkflowGenome) -> WorkflowGenome:
        """Change la stratégie de délégation du supervisor."""
        child = copy.deepcopy(genome)
        child.id = str(uuid.uuid4())
        child.parent_ids = [genome.id]

        strategies = ["auto", "sequential", "parallel"]
        child.delegation_strategy = random.choice(
            [s for s in strategies if s != child.delegation_strategy]
        )

        child.mutation_history.append(
            f"mutate_delegation_strategy:{child.delegation_strategy}"
        )
        return child

    def mutate_max_turns(self, genome: WorkflowGenome) -> WorkflowGenome:
        """Ajuste le nombre maximum de tours de conversation."""
        child = copy.deepcopy(genome)
        child.id = str(uuid.uuid4())
        child.parent_ids = [genome.id]

        delta = random.choice([-3, -2, -1, 1, 2, 3])
        child.max_turns = max(3, min(25, child.max_turns + delta))

        child.mutation_history.append(f"mutate_max_turns:{child.max_turns}")
        return child


### 2.5 Validation Post-Génération

```python
from dataclasses import dataclass

@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    auto_fixed: bool = False

class GenomeValidator:
    """Valide la cohérence d'un génome après crossover/mutation."""

    def validate(self, genome: WorkflowGenome) -> ValidationResult:
        errors = []
        warnings = []
        auto_fixed = False

        # --- Règle 1 : Le supervisor doit exister ---
        if not genome.supervisor or not genome.supervisor.system_prompt:
            errors.append("Le supervisor n'a pas de system prompt")

        # --- Règle 2 : Au moins 1 sub-agent ---
        if len(genome.sub_agents) < 1:
            errors.append("Le workflow doit avoir au moins 1 sub-agent")

        # --- Règle 3 : Pas de doublons de rôles ---
        roles = [a.role for a in genome.sub_agents]
        if len(roles) != len(set(roles)):
            duplicates = [r for r in roles if roles.count(r) > 1]
            warnings.append(f"Rôles dupliqués détectés : {set(duplicates)}")
            # Auto-fix : garder le premier de chaque rôle
            seen = set()
            genome.sub_agents = [
                a for a in genome.sub_agents
                if a.role not in seen and not seen.add(a.role)
            ]
            auto_fixed = True

        # --- Règle 4 : Tous les tool_ids référencent des tools existants ---
        valid_tool_names = {t.name for t in genome.tools}
        for agent in [genome.supervisor] + genome.sub_agents:
            orphan_tools = [
                tid for tid in agent.tool_ids if tid not in valid_tool_names
            ]
            if orphan_tools:
                warnings.append(
                    f"Agent '{agent.role}' référence des tools inexistants : {orphan_tools}"
                )
                agent.tool_ids = [
                    tid for tid in agent.tool_ids if tid in valid_tool_names
                ]
                auto_fixed = True

        # --- Règle 5 : Pas de prompts vides ---
        for agent in [genome.supervisor] + genome.sub_agents:
            if len(agent.system_prompt.strip()) < 20:
                errors.append(
                    f"Agent '{agent.role}' a un prompt trop court ({len(agent.system_prompt)} chars)"
                )

        # --- Règle 6 : Pas de cycles dans la hiérarchie ---
        # (Dans notre modèle, le supervisor est toujours la racine,
        #  et les sub-agents sont à un seul niveau -- pas de cycles possibles)
        # Cette vérification serait nécessaire si on permettait des sub-sub-agents.

        # --- Règle 7 : Paramètres dans les bornes ---
        for agent in [genome.supervisor] + genome.sub_agents:
            if not (0.0 <= agent.temperature <= 2.0):
                agent.temperature = max(0.0, min(2.0, agent.temperature))
                auto_fixed = True
            if not (256 <= agent.max_tokens <= 16384):
                agent.max_tokens = max(256, min(16384, agent.max_tokens))
                auto_fixed = True
            if agent.model not in ["haiku", "sonnet", "opus", "inherit"]:
                agent.model = "haiku"
                auto_fixed = True

        # --- Règle 8 : Taille raisonnable du workflow ---
        if len(genome.sub_agents) > 8:
            warnings.append(
                f"Trop de sub-agents ({len(genome.sub_agents)}). "
                "Risque de coût élevé et de confusion du supervisor."
            )
        if len(genome.tools) > 15:
            warnings.append(
                f"Trop de tools ({len(genome.tools)}). "
                "Le supervisor pourrait avoir du mal à choisir."
            )

        # --- Règle 9 : Chaque tool est utilisé par au moins un agent ---
        used_tools = set()
        for agent in [genome.supervisor] + genome.sub_agents:
            used_tools.update(agent.tool_ids)
        unused_tools = valid_tool_names - used_tools
        if unused_tools:
            warnings.append(f"Tools inutilisés (orphelins) : {unused_tools}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            auto_fixed=auto_fixed
        )
```

### 2.6 Dynamique Générationnelle Bi-Phasée

```python
@dataclass
class EvolutionPhaseConfig:
    """Configuration des phases d'évolution."""
    # Phase 1 : Exploration
    exploration_generations: int = 80
    exploration_mutation_rate: float = 0.40   # 40% de chance de mutation
    exploration_crossover_rate: float = 0.50  # 50% de chance de crossover
    exploration_elite_ratio: float = 0.10     # 10% d'élitisme
    exploration_tournament_size: int = 3
    exploration_mutations: dict = None  # Poids des types de mutation

    # Phase 2 : Optimisation
    optimization_generations: int = 120
    optimization_mutation_rate: float = 0.15  # 15% -- mutations fines
    optimization_crossover_rate: float = 0.30 # 30%
    optimization_elite_ratio: float = 0.25    # 25% d'élitisme (conservation)
    optimization_tournament_size: int = 5
    optimization_mutations: dict = None  # Poids des types de mutation

    def __post_init__(self):
        if self.exploration_mutations is None:
            self.exploration_mutations = {
                "prompt_paraphrase": 0.15,
                "prompt_injection": 0.15,
                "parameters": 0.10,
                "tool_description": 0.10,
                "add_agent": 0.15,
                "remove_agent": 0.10,
                "rewire_tools": 0.10,
                "delegation_strategy": 0.10,
                "max_turns": 0.05,
            }
        if self.optimization_mutations is None:
            self.optimization_mutations = {
                "prompt_paraphrase": 0.30,  # Fine-tuning des prompts
                "prompt_injection": 0.05,
                "parameters": 0.25,         # Ajustement fin des paramètres
                "tool_description": 0.15,
                "add_agent": 0.02,          # Structure quasi-figée
                "remove_agent": 0.02,
                "rewire_tools": 0.10,
                "delegation_strategy": 0.05,
                "max_turns": 0.06,
            }
```

---

## 3. Bootstrap et Séquence de Démarrage

### 3.1 Création du Gold Standard (Couche 0)

Le gold standard est un ensemble de ~50 paires `(query, réponse_attendue)` validées humainement. C'est l'ancrage de vérité qui empêche la dérive évolutive.

**Processus de création en 4 étapes :**

```python
# Étape 1 : Extraction automatique des questions depuis le contenu du cours
COURSE_EXTRACTION_PROMPT = """Tu es un expert en ingénierie pédagogique.

Voici le contenu d'un cours :
---
{course_content}
---

Génère exactement 60 questions pédagogiques couvrant :
- 15 questions factuelles (définitions, dates, noms)
- 15 questions de compréhension (expliquer un concept, comparer)
- 15 questions d'application (résoudre un problème, appliquer une méthode)
- 10 questions de synthèse (relier plusieurs concepts)
- 5 questions pièges (erreurs courantes, confusions fréquentes)

Pour chaque question, indique :
- La question
- Le niveau de difficulté (1-5)
- Les concepts clés impliqués
- La section du cours concernée

Format JSON :
[{{"question": "...", "difficulty": N, "concepts": ["..."], "section": "..."}}]
"""

# Étape 2 : Génération des réponses de référence par un expert LLM
REFERENCE_ANSWER_PROMPT = """Tu es un professeur expert du domaine.

Question : {question}
Contenu du cours pertinent : {relevant_section}

Rédige une réponse pédagogique de référence qui :
1. Répond précisément à la question
2. Cite les éléments du cours
3. Est structurée clairement
4. A le niveau de détail approprié pour un étudiant
5. Est factuelle et vérifiable

Cette réponse servira de gold standard pour évaluer des agents IA.
"""

# Étape 3 : Validation humaine (interface simplifiée)
# Fichier YAML pour la revue humaine
GOLD_STANDARD_TEMPLATE = """
# Gold Standard - {course_name}
# Validé par : {reviewer_name}
# Date : {date}

pairs:
  - id: "gs-001"
    query: "Qu'est-ce que la programmation orientée objet ?"
    difficulty: 2
    concepts: ["POO", "paradigmes"]
    expected_answer: |
      La programmation orientée objet (POO) est un paradigme de programmation
      qui organise le code autour d'objets...
    evaluation_criteria:
      must_mention: ["encapsulation", "héritage", "polymorphisme"]
      must_not_mention: []
      min_length: 100
      max_length: 500
    human_validated: true
    reviewer_notes: "Bonne couverture des 4 piliers"
"""
```

**Workflow de création concret :**

```
1. Charger le contenu du cours (PDF/Markdown)
2. Opus 4.6 génère 60 questions diversifiées
3. Opus 4.6 génère les réponses de référence pour chaque question
4. Un expert humain valide/corrige les 60 paires
5. Sélection des 50 meilleures paires (rejet des ambiguës)
6. Stockage en YAML versionné Git
7. Split : 40 pour l'évaluation, 10 pour la validation (jamais vus en entraînement)
```

**Estimation du coût de création du gold standard :**

| Étape | Modèle | Tokens estimés | Coût |
|-------|--------|---------------|------|
| Extraction questions | Opus 4.6 | ~10K in + 5K out | ~$0.175 |
| Génération réponses (60x) | Opus 4.6 | ~120K in + 60K out | ~$2.10 |
| **Total** | | | **~$2.30** |

Le temps humain de validation (~2-4h) est le vrai coût.

### 3.2 Génération de la Population Initiale

La population initiale (Génération 0) est composée de workflows "naïfs" construits à partir de templates variés :

```python
class PopulationInitializer:
    """Génère la population initiale de workflows."""

    # Templates de supervisor
    SUPERVISOR_TEMPLATES = [
        {
            "style": "directive",
            "prompt": """Tu es un coordinateur pédagogique. Tu reçois des questions d'étudiants et tu délègues le travail à tes agents spécialisés.

## Processus
1. Analyse la question de l'étudiant
2. Identifie les compétences nécessaires
3. Délègue aux agents appropriés
4. Synthétise leurs contributions en une réponse cohérente

## Règles
- Toujours vérifier la cohérence de la réponse finale
- Adapter le niveau au public cible
- Citer les sources du cours quand possible"""
        },
        {
            "style": "socratique",
            "prompt": """Tu es un tuteur socratique. Plutôt que de donner des réponses directes, tu guides l'étudiant vers la compréhension par le questionnement.

## Approche
1. Comprends la question de fond
2. Utilise tes agents pour rassembler les éléments de réponse
3. Formule une réponse qui amène l'étudiant à réfléchir
4. Inclus des questions de relance

## Principes
- Ne jamais donner la réponse brute sans explication
- Toujours connecter au vécu de l'étudiant
- Encourager l'auto-évaluation"""
        },
        {
            "style": "structuré",
            "prompt": """Tu es un assistant pédagogique structuré. Tu réponds aux questions en suivant un format rigoureux et reproductible.

## Format de réponse
1. **Résumé** : réponse en 1-2 phrases
2. **Développement** : explication détaillée avec sous-sections
3. **Exemples** : cas concrets d'application
4. **Points clés** : bullet points des éléments essentiels
5. **Pour aller plus loin** : concepts connexes à explorer

## Délégation
- Utilise l'agent de recherche pour les faits
- Utilise l'agent d'exemples pour les illustrations
- Utilise l'agent de synthèse pour le résumé"""
        },
    ]

    # Templates de sub-agents
    SUBAGENT_TEMPLATES = [
        AgentGene(role="researcher", system_prompt="Tu es un chercheur spécialisé. Tu extrais les informations pertinentes du cours pour répondre à la question posée. Sois précis et cite tes sources.", model="haiku", temperature=0.3),
        AgentGene(role="explainer", system_prompt="Tu es un pédagogue expert. Tu expliques les concepts de manière claire, progressive et accessible. Tu utilises des analogies et des exemples.", model="sonnet", temperature=0.7),
        AgentGene(role="example_generator", system_prompt="Tu génères des exemples concrets et des exercices pratiques pour illustrer les concepts. Varie les contextes d'application.", model="haiku", temperature=0.9),
        AgentGene(role="simplifier", system_prompt="Tu reformules les explications complexes en langage simple. Tu cibles un niveau de compréhension débutant.", model="haiku", temperature=0.6),
        AgentGene(role="fact_checker", system_prompt="Tu vérifies la précision factuelle des réponses. Tu signales les erreurs, imprécisions et généralisations abusives.", model="sonnet", temperature=0.1),
        AgentGene(role="synthesizer", system_prompt="Tu produis des synthèses concises. Tu identifies les 3-5 points clés et les formules de manière mémorable.", model="haiku", temperature=0.5),
    ]

    # Templates de tools
    TOOL_TEMPLATES = [
        ToolGene(name="search_course", description="Recherche dans le contenu du cours les passages pertinents pour la question.", schema={"query": str}),
        ToolGene(name="get_definition", description="Obtient la définition précise d'un terme ou concept du cours.", schema={"term": str}),
        ToolGene(name="get_examples", description="Récupère des exemples liés à un concept depuis la base du cours.", schema={"concept": str}),
        ToolGene(name="check_prerequisite", description="Vérifie les prérequis nécessaires pour comprendre un concept.", schema={"concept": str}),
        ToolGene(name="get_related_concepts", description="Trouve les concepts liés et les connexions avec d'autres parties du cours.", schema={"concept": str}),
    ]

    def generate_initial_population(
        self,
        population_size: int = 50,
        min_agents: int = 2,
        max_agents: int = 5
    ) -> list[WorkflowGenome]:
        """Génère une population initiale diversifiée."""
        population = []

        for i in range(population_size):
            genome = WorkflowGenome()
            genome.generation = 0

            # Choisir un template de supervisor
            supervisor_template = random.choice(self.SUPERVISOR_TEMPLATES)
            genome.supervisor = AgentGene(
                role="supervisor",
                system_prompt=supervisor_template["prompt"],
                model=random.choice(["sonnet", "sonnet", "haiku"]),  # 2/3 sonnet
                temperature=random.uniform(0.3, 0.9)
            )

            # Choisir N sub-agents aléatoirement
            n_agents = random.randint(min_agents, max_agents)
            selected_agents = random.sample(
                self.SUBAGENT_TEMPLATES,
                min(n_agents, len(self.SUBAGENT_TEMPLATES))
            )
            genome.sub_agents = [copy.deepcopy(a) for a in selected_agents]

            # Assigner un nouvel ID à chaque agent
            for agent in genome.sub_agents:
                agent.id = str(uuid.uuid4())[:8]
                # Varier légèrement la température
                agent.temperature += random.gauss(0, 0.1)
                agent.temperature = max(0.0, min(1.5, agent.temperature))

            # Choisir les tools
            n_tools = random.randint(2, len(self.TOOL_TEMPLATES))
            genome.tools = [
                copy.deepcopy(t)
                for t in random.sample(self.TOOL_TEMPLATES, n_tools)
            ]

            # Assigner les tools aux agents
            tool_names = [t.name for t in genome.tools]
            genome.supervisor.tool_ids = tool_names  # Le supervisor a tous les tools
            for agent in genome.sub_agents:
                n_agent_tools = random.randint(1, len(tool_names))
                agent.tool_ids = random.sample(tool_names, n_agent_tools)

            # Paramètres globaux
            genome.max_turns = random.choice([5, 8, 10, 12, 15])
            genome.delegation_strategy = random.choice(
                ["auto", "auto", "sequential", "parallel"]
            )

            population.append(genome)

        return population
```

### 3.3 Amorçage des Évaluateurs (Population B)

Les évaluateurs sont eux-mêmes des génomes qui évoluent. Voici comment les amorcer :

```python
class EvaluatorInitializer:
    """Initialise la population d'évaluateurs (Population B)."""

    # Les 19 critères d'évaluation
    EVALUATION_CRITERIA = {
        # --- Critères MICRO (12) --- évaluables par Haiku ---
        "grammar": "Correction grammaticale et orthographique",
        "formatting": "Qualité du formatage (titres, listes, structure visuelle)",
        "length_appropriateness": "Longueur appropriée (ni trop court, ni trop long)",
        "terminology_accuracy": "Utilisation correcte du vocabulaire technique du domaine",
        "source_citation": "Références au contenu du cours quand pertinent",
        "response_completeness": "La réponse couvre tous les aspects de la question",
        "clarity": "Clarté et lisibilité des explications",
        "example_quality": "Qualité et pertinence des exemples fournis",
        "logical_structure": "Organisation logique et progression des idées",
        "prerequisite_handling": "Gestion des prérequis (rappels nécessaires)",
        "error_absence": "Absence d'erreurs factuelles ou de contresens",
        "tone_appropriateness": "Ton adapté (ni condescendant, ni trop technique)",

        # --- Critères MÉSO (5) --- nécessitent Sonnet ---
        "pedagogical_value": "Valeur pédagogique globale de la réponse",
        "concept_depth": "Profondeur de traitement des concepts",
        "critical_thinking": "Stimulation de la réflexion critique de l'étudiant",
        "knowledge_transfer": "Efficacité du transfert de connaissances",
        "adaptability": "Capacité d'adaptation au niveau de l'étudiant",

        # --- Critères MACRO (2) --- nécessitent Sonnet/Opus ---
        "overall_quality": "Qualité globale holistique de la réponse",
        "ground_truth_alignment": "Alignement avec la réponse de référence (Couche 0)",
    }

    def generate_evaluator_genome(self, criteria_subset: list[str]) -> dict:
        """Génère un génome d'évaluateur pour un sous-ensemble de critères."""

        criteria_descriptions = "\n".join([
            f"- **{c}** : {self.EVALUATION_CRITERIA[c]}"
            for c in criteria_subset
        ])

        system_prompt = f"""Tu es un évaluateur expert en pédagogie et en qualité de réponses IA.

## Ta mission
Évalue la qualité d'une réponse pédagogique selon les critères suivants :

{criteria_descriptions}

## Format d'évaluation
Pour chaque critère, fournis :
1. Un score de 0 à 10 (0 = catastrophique, 10 = parfait)
2. Une justification en 1-2 phrases

## Règles
- Sois objectif et cohérent entre les évaluations
- Un score de 5 = acceptable mais améliorable
- Un score de 8+ = excellence, réservé aux réponses vraiment remarquables
- Justifie TOUJOURS un score < 4 ou > 8 avec des éléments précis
- Compare à la réponse de référence quand elle est fournie

Réponds UNIQUEMENT au format JSON :
{{
  "scores": {{{", ".join([f'"{c}": {{"score": N, "reasoning": "..."}}' for c in criteria_subset])}}},
  "overall_comment": "..."
}}"""

        return {
            "id": str(uuid.uuid4()),
            "type": "evaluator",
            "criteria": criteria_subset,
            "system_prompt": system_prompt,
            "model": "haiku" if all(
                c in list(self.EVALUATION_CRITERIA.keys())[:12]
                for c in criteria_subset
            ) else "sonnet",
            "temperature": 0.2,  # Basse pour la cohérence
            "generation": 0
        }

    def generate_initial_evaluator_population(
        self, population_size: int = 20
    ) -> list[dict]:
        """Génère la population initiale d'évaluateurs."""
        evaluators = []
        criteria_list = list(self.EVALUATION_CRITERIA.keys())

        # Stratégie : chaque évaluateur couvre 3-7 critères
        for _ in range(population_size):
            n_criteria = random.randint(3, 7)
            subset = random.sample(criteria_list, n_criteria)
            evaluator = self.generate_evaluator_genome(subset)
            evaluators.append(evaluator)

        # Ajouter des évaluateurs spécialisés garantis
        # Un évaluateur full-micro
        evaluators.append(
            self.generate_evaluator_genome(criteria_list[:12])
        )
        # Un évaluateur full-méso
        evaluators.append(
            self.generate_evaluator_genome(criteria_list[12:17])
        )
        # Un évaluateur full-macro
        evaluators.append(
            self.generate_evaluator_genome(criteria_list[17:])
        )

        return evaluators
```

### 3.4 Amorçage des Queries Adversariaux (Population C)

```python
class AdversarialInitializer:
    """Initialise la population de queries adversariaux (Population C)."""

    ADVERSARIAL_TEMPLATES = [
        # Questions ambiguës
        "Explique {concept_a} et {concept_b}",  # Trop vague, quel lien ?

        # Questions hors périmètre
        "Quel est le lien entre {concept} et la physique quantique ?",

        # Questions mal formulées
        "{concept} c'est quoi exactement ?",

        # Questions piège (erreur dans la question)
        "Pourquoi dit-on que {concept_a} est un sous-type de {concept_b} ?",  # Faux

        # Questions très spécifiques (edge case)
        "Dans quel cas précis {concept} ne s'applique-t-il PAS ?",

        # Questions multi-concepts (surcharge cognitive)
        "Compare {concept_a}, {concept_b} et {concept_c} en termes de {aspect}.",

        # Questions nécessitant du raisonnement
        "Si on supprimait {concept} du cours, quelles seraient les conséquences ?",
    ]

    async def agenerate_initial_adversarial_population(
        self,
        course_concepts: list[str],
        population_size: int = 30,
        llm_client: AsyncAnthropic = None
    ) -> list[dict]:
        """Génère des queries adversariaux initiaux."""
        queries = []

        # Phase 1 : Templates avec concepts du cours
        for _ in range(population_size // 2):
            template = random.choice(self.ADVERSARIAL_TEMPLATES)
            concepts = random.sample(
                course_concepts, min(3, len(course_concepts))
            )
            query_text = template
            for i, placeholder in enumerate(
                re.findall(r'\{concept(?:_[a-c])?\}', template)
            ):
                if i < len(concepts):
                    query_text = query_text.replace(
                        placeholder, concepts[i], 1
                    )
            queries.append({
                "id": str(uuid.uuid4()),
                "type": "adversarial_query",
                "query": query_text,
                "difficulty": random.randint(1, 5),
                "strategy": "template",
                "generation": 0
            })

        # Phase 2 : Génération LLM de queries adversariaux
        if llm_client:
            response = await llm_client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=4096,
                temperature=1.0,
                messages=[{
                    "role": "user",
                    "content": f"""Génère {population_size // 2} questions pédagogiques adversariales sur les concepts suivants : {', '.join(course_concepts)}.

Les questions doivent être conçues pour mettre en difficulté un agent IA pédagogique :
- Questions ambiguës ou mal formulées
- Questions piège avec des présupposés faux
- Questions nécessitant de l'esprit critique
- Questions hors périmètre du cours
- Questions combinant plusieurs concepts de manière inattendue

Format JSON : [{{"query": "...", "difficulty": 1-5, "strategy": "type_de_piège"}}]"""
                }]
            )

            import json
            try:
                generated = json.loads(response.content[0].text)
                for item in generated:
                    item["id"] = str(uuid.uuid4())
                    item["type"] = "adversarial_query"
                    item["generation"] = 0
                    queries.append(item)
            except json.JSONDecodeError:
                pass  # Fallback : utiliser uniquement les templates

        return queries
```

---

## 4. Architecture du Code

### 4.1 Structure du Projet Python

```
eduflow-evolution/
├── pyproject.toml
├── README.md
├── .env.example
├── config/
│   ├── evolution.yaml          # Paramètres de l'algorithme génétique
│   ├── models.yaml             # Configuration des modèles LLM
│   └── courses/
│       └── example_course/
│           ├── content.md      # Contenu du cours
│           └── gold_standard.yaml  # 50 paires (query, réponse)
│
├── src/
│   ├── __init__.py
│   │
│   ├── genome/                 # Représentation et manipulation des génomes
│   │   ├── __init__.py
│   │   ├── types.py            # WorkflowGenome, AgentGene, ToolGene
│   │   ├── serialization.py    # Sérialisation JSON/YAML
│   │   └── validation.py       # GenomeValidator
│   │
│   ├── operators/              # Opérateurs génétiques
│   │   ├── __init__.py
│   │   ├── crossover.py        # PromptCrossover, StructuralCrossover
│   │   ├── mutation.py         # MutationOperators
│   │   ├── selection.py        # TournamentSelection, ElitistSelection
│   │   └── registry.py         # Registre des opérateurs avec poids
│   │
│   ├── population/             # Gestion des populations
│   │   ├── __init__.py
│   │   ├── individual.py       # Individual (wrapper genome + fitness)
│   │   ├── population.py       # Population (collection d'individus)
│   │   ├── initializer.py      # PopulationInitializer, EvaluatorInit, AdversarialInit
│   │   └── diversity.py        # Métriques de diversité
│   │
│   ├── fitness/                # Évaluation et fitness
│   │   ├── __init__.py
│   │   ├── evaluator.py        # Evaluator (exécute les évaluateurs Pop. B)
│   │   ├── fitness_vector.py   # FitnessVector (19 dimensions)
│   │   ├── aggregation.py      # Agrégation multi-critères -> scalaire
│   │   ├── ground_truth.py     # GroundTruthEvaluator (Couche 0)
│   │   └── jurisprudence.py    # JurisprudenceMemory (M3)
│   │
│   ├── execution/              # Exécution des workflows
│   │   ├── __init__.py
│   │   ├── materializer.py     # Genome -> ClaudeAgentOptions
│   │   ├── runner.py           # AsyncExecutionEngine
│   │   ├── telemetry.py        # TelemetryCollector (M1)
│   │   └── rate_limiter.py     # TokenBucketRateLimiter
│   │
│   ├── evolution/              # Boucle principale d'évolution
│   │   ├── __init__.py
│   │   ├── engine.py           # EvolutionEngine (boucle principale)
│   │   ├── generation.py       # Generation (une itération complète)
│   │   ├── phase.py            # EvolutionPhaseConfig, PhaseManager
│   │   └── coevolution.py      # CoevolutionManager (3 populations)
│   │
│   ├── storage/                # Persistance
│   │   ├── __init__.py
│   │   ├── database.py         # SQLite async (aiosqlite)
│   │   ├── file_store.py       # Stockage fichiers (réponses brutes)
│   │   └── gold_standard.py    # Chargement du gold standard YAML
│   │
│   └── monitoring/             # Observabilité
│       ├── __init__.py
│       ├── dashboard.py        # Rich-based terminal dashboard
│       ├── metrics.py          # Métriques d'évolution
│       └── export.py           # Export CSV/JSON pour analyse
│
├── tests/
│   ├── test_genome.py
│   ├── test_operators.py
│   ├── test_fitness.py
│   ├── test_execution.py
│   └── test_evolution.py
│
├── scripts/
│   ├── create_gold_standard.py     # Création assistée du gold standard
│   ├── run_evolution.py            # Point d'entrée principal
│   ├── analyze_results.py          # Analyse post-évolution
│   └── export_best_workflow.py     # Exporte le meilleur workflow
│
└── data/
    ├── eduflow.db                  # Base SQLite
    ├── responses/                  # Réponses brutes (JSON)
    └── logs/                       # Logs JSONL d'évolution
```

### 4.2 Classes Principales

```python
# ===== src/population/individual.py =====

from dataclasses import dataclass, field
from typing import Optional
import numpy as np

@dataclass
class Individual:
    """Un individu dans l'une des 3 populations."""
    genome: dict                           # Le génome (WorkflowGenome, Evaluator, ou Query)
    population_type: str                   # 'workflow', 'evaluator', 'adversarial'
    fitness_vector: Optional[np.ndarray] = None  # Vecteur 19D pour les workflows
    fitness_scalar: float = 0.0            # Fitness agrégée
    generation: int = 0
    is_elite: bool = False
    evaluation_count: int = 0              # Nombre de fois évalué
    metadata: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.genome.get("id", "unknown")

    def dominates(self, other: "Individual") -> bool:
        """Dominance de Pareto : self domine other si meilleur sur tous les critères."""
        if self.fitness_vector is None or other.fitness_vector is None:
            return self.fitness_scalar > other.fitness_scalar
        return (
            np.all(self.fitness_vector >= other.fitness_vector) and
            np.any(self.fitness_vector > other.fitness_vector)
        )


# ===== src/population/population.py =====

class Population:
    """Collection d'individus avec opérations de sélection."""

    def __init__(self, individuals: list[Individual] = None):
        self.individuals = individuals or []

    def select_tournament(self, k: int, tournament_size: int = 3) -> list[Individual]:
        """Sélection par tournoi."""
        selected = []
        for _ in range(k):
            competitors = random.sample(self.individuals, tournament_size)
            winner = max(competitors, key=lambda ind: ind.fitness_scalar)
            selected.append(winner)
        return selected

    def select_elite(self, ratio: float = 0.1) -> list[Individual]:
        """Sélection élitiste : top N%."""
        n = max(1, int(len(self.individuals) * ratio))
        sorted_pop = sorted(
            self.individuals, key=lambda ind: ind.fitness_scalar, reverse=True
        )
        return sorted_pop[:n]

    def compute_diversity(self) -> float:
        """Mesure de diversité basée sur la distance des fitness vectors."""
        if len(self.individuals) < 2:
            return 0.0
        vectors = [
            ind.fitness_vector for ind in self.individuals
            if ind.fitness_vector is not None
        ]
        if len(vectors) < 2:
            return 0.0
        vectors = np.array(vectors)
        # Distance moyenne entre tous les individus
        from scipy.spatial.distance import pdist
        return float(np.mean(pdist(vectors)))

    @property
    def best(self) -> Individual:
        return max(self.individuals, key=lambda ind: ind.fitness_scalar)

    @property
    def stats(self) -> dict:
        fitnesses = [ind.fitness_scalar for ind in self.individuals]
        return {
            "size": len(self.individuals),
            "fitness_min": min(fitnesses) if fitnesses else 0,
            "fitness_max": max(fitnesses) if fitnesses else 0,
            "fitness_mean": np.mean(fitnesses) if fitnesses else 0,
            "fitness_std": np.std(fitnesses) if fitnesses else 0,
            "diversity": self.compute_diversity()
        }
```

### 4.3 Boucle Principale d'Évolution

```python
# ===== src/evolution/engine.py =====

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger("eduflow")

class EvolutionEngine:
    """Moteur principal de l'algorithme évolutif co-évolutif."""

    def __init__(
        self,
        config: EvolutionPhaseConfig,
        execution_engine: AsyncExecutionEngine,
        mutation_operators: MutationOperators,
        prompt_crossover: PromptCrossover,
        structural_crossover: StructuralCrossover,
        genome_validator: GenomeValidator,
        gold_standard: list[dict],
        database: "AsyncDatabase",
    ):
        self.config = config
        self.execution = execution_engine
        self.mutation = mutation_operators
        self.prompt_xover = prompt_crossover
        self.struct_xover = structural_crossover
        self.validator = genome_validator
        self.gold_standard = gold_standard
        self.db = database

        # Les 3 populations co-évolutives
        self.pop_workflows: Population = Population()
        self.pop_evaluators: Population = Population()
        self.pop_adversarial: Population = Population()

        # État
        self.current_generation: int = 0
        self.current_phase: str = "exploration"
        self.best_ever: Individual = None
        self.jurisprudence: list[dict] = []  # Mémoire M3

    async def ainitialize(self):
        """Bootstrap : génère les 3 populations initiales."""
        logger.info("Initialisation des populations...")

        # Population A : Workflows
        wf_init = PopulationInitializer()
        workflows = wf_init.generate_initial_population(population_size=50)
        self.pop_workflows = Population([
            Individual(genome=wf.to_dict(), population_type="workflow")
            for wf in workflows
        ])

        # Population B : Évaluateurs
        eval_init = EvaluatorInitializer()
        evaluators = eval_init.generate_initial_evaluator_population(population_size=20)
        self.pop_evaluators = Population([
            Individual(genome=ev, population_type="evaluator")
            for ev in evaluators
        ])

        # Population C : Queries adversariaux
        adv_init = AdversarialInitializer()
        adversarials = await adv_init.agenerate_initial_adversarial_population(
            course_concepts=self._extract_concepts(),
            population_size=30
        )
        self.pop_adversarial = Population([
            Individual(genome=q, population_type="adversarial")
            for q in adversarials
        ])

        logger.info(
            f"Populations initialisées : "
            f"{len(self.pop_workflows.individuals)} workflows, "
            f"{len(self.pop_evaluators.individuals)} évaluateurs, "
            f"{len(self.pop_adversarial.individuals)} queries"
        )

    async def arun(self):
        """Boucle principale d'évolution."""
        await self.ainitialize()

        total_generations = (
            self.config.exploration_generations +
            self.config.optimization_generations
        )

        for gen in range(total_generations):
            self.current_generation = gen
            self.current_phase = (
                "exploration" if gen < self.config.exploration_generations
                else "optimization"
            )

            logger.info(
                f"\n{'='*60}\n"
                f"GÉNÉRATION {gen}/{total_generations} "
                f"[Phase: {self.current_phase}]\n"
                f"{'='*60}"
            )

            start_time = datetime.now()

            # --- Étape 1 : Évaluation de la population courante ---
            await self._aevaluate_population()

            # --- Étape 2 : Calibration par ground truth (1 fois sur 5) ---
            if gen % 5 == 0:
                await self._acalibrate_with_ground_truth()

            # --- Étape 3 : Sélection ---
            phase_config = self._get_phase_config()
            elite = self.pop_workflows.select_elite(phase_config["elite_ratio"])
            parents = self.pop_workflows.select_tournament(
                k=len(self.pop_workflows.individuals) - len(elite),
                tournament_size=phase_config["tournament_size"]
            )

            # --- Étape 4 : Reproduction (crossover + mutation) ---
            offspring = await self._aproduce_offspring(
                parents, phase_config
            )

            # --- Étape 5 : Validation et remplacement ---
            valid_offspring = self._validate_offspring(offspring)
            self.pop_workflows = Population(
                [ind for ind in elite] + valid_offspring
            )

            # --- Étape 6 : Co-évolution des évaluateurs et queries ---
            if gen % 3 == 0:  # Tous les 3 générations
                await self._acoevolve_evaluators()
            if gen % 5 == 0:  # Tous les 5 générations
                await self._acoevolve_adversarial()

            # --- Étape 7 : Mise à jour de la jurisprudence (M3) ---
            self._update_jurisprudence()

            # --- Étape 8 : Logging et sauvegarde ---
            duration = (datetime.now() - start_time).total_seconds()
            stats = self.pop_workflows.stats

            if self.best_ever is None or self.pop_workflows.best.fitness_scalar > self.best_ever.fitness_scalar:
                self.best_ever = self.pop_workflows.best

            logger.info(
                f"Génération {gen} terminée en {duration:.1f}s | "
                f"Fitness: min={stats['fitness_min']:.3f} "
                f"avg={stats['fitness_mean']:.3f} "
                f"max={stats['fitness_max']:.3f} | "
                f"Diversité: {stats['diversity']:.3f} | "
                f"Best ever: {self.best_ever.fitness_scalar:.3f}"
            )

            await self.db.asave_generation(gen, self.current_phase, stats,
                                           self.pop_workflows)

        # Fin de l'évolution
        logger.info(f"\nÉvolution terminée. Meilleur individu : {self.best_ever.id}")
        return self.best_ever

    async def _aevaluate_population(self):
        """Évalue tous les individus de la population workflows."""
        # Sélectionner les queries (mix gold standard + adversarial)
        gold_queries = random.sample(
            self.gold_standard, min(10, len(self.gold_standard))
        )
        adv_queries = random.sample(
            self.pop_adversarial.individuals,
            min(5, len(self.pop_adversarial.individuals))
        )
        all_queries = (
            [gq["query"] for gq in gold_queries] +
            [aq.genome["query"] for aq in adv_queries]
        )

        # Sélectionner les évaluateurs
        evaluators = random.sample(
            self.pop_evaluators.individuals,
            min(5, len(self.pop_evaluators.individuals))
        )

        # Exécuter les workflows sur les queries
        results = await self.execution.aexecute_generation(
            workflows=[ind.genome for ind in self.pop_workflows.individuals],
            queries=all_queries,
            evaluators=[ev.genome for ev in evaluators]
        )

        # Agréger les scores en fitness vectors
        for ind in self.pop_workflows.individuals:
            ind_results = [r for r in results if r.get("individual_id") == ind.id]
            if ind_results:
                scores = self._aggregate_scores(ind_results)
                ind.fitness_vector = np.array(scores)
                ind.fitness_scalar = self._compute_scalar_fitness(scores)
                ind.evaluation_count += 1

    async def _aproduce_offspring(
        self, parents: list[Individual], config: dict
    ) -> list[Individual]:
        """Produit la génération suivante via crossover et mutation."""
        offspring = []

        for i in range(0, len(parents), 2):
            if i + 1 >= len(parents):
                break

            parent_a = parents[i]
            parent_b = parents[i + 1]

            # Crossover
            if random.random() < config["crossover_rate"]:
                child_genome = await self._acrossover(parent_a, parent_b)
            else:
                child_genome = copy.deepcopy(
                    random.choice([parent_a, parent_b]).genome
                )

            # Mutation
            if random.random() < config["mutation_rate"]:
                child_genome = await self._amutate(
                    child_genome, config["mutations"]
                )

            child = Individual(
                genome=child_genome,
                population_type="workflow",
                generation=self.current_generation + 1
            )
            offspring.append(child)

        return offspring

    async def _acrossover(
        self, parent_a: Individual, parent_b: Individual
    ) -> dict:
        """Applique un crossover entre deux parents."""
        genome_a = WorkflowGenome.from_dict(parent_a.genome)
        genome_b = WorkflowGenome.from_dict(parent_b.genome)

        # Choisir le type de crossover
        xover_type = random.choice([
            "prompt_sections", "swap_agents", "swap_tools", "supervisor_blend"
        ])

        if xover_type == "prompt_sections":
            child = copy.deepcopy(genome_a)
            child.supervisor.system_prompt = self.prompt_xover.crossover_by_sections(
                genome_a.supervisor.system_prompt,
                genome_b.supervisor.system_prompt
            )
        elif xover_type == "swap_agents":
            child = self.struct_xover.crossover_swap_agents(genome_a, genome_b)
        elif xover_type == "swap_tools":
            child = self.struct_xover.crossover_swap_tools(genome_a, genome_b)
        else:
            child = self.struct_xover.crossover_supervisor_blend(genome_a, genome_b)

        child.generation = self.current_generation + 1
        return child.to_dict()

    async def _amutate(self, genome_dict: dict, mutation_weights: dict) -> dict:
        """Applique une mutation pondérée."""
        genome = WorkflowGenome.from_dict(genome_dict)

        # Sélection pondérée du type de mutation
        mutation_types = list(mutation_weights.keys())
        weights = list(mutation_weights.values())
        chosen = random.choices(mutation_types, weights=weights, k=1)[0]

        mutation_map = {
            "prompt_paraphrase": self.mutation.amutate_prompt_paraphrase,
            "prompt_injection": self.mutation.amutate_prompt_injection,
            "parameters": lambda g: self.mutation.mutate_parameters(g),
            "tool_description": lambda g: self.mutation.mutate_tool_description(g),
            "add_agent": lambda g: self.mutation.mutate_add_agent(g),
            "remove_agent": lambda g: self.mutation.mutate_remove_agent(g),
            "rewire_tools": lambda g: self.mutation.mutate_rewire_tools(g),
            "delegation_strategy": lambda g: self.mutation.mutate_delegation_strategy(g),
            "max_turns": lambda g: self.mutation.mutate_max_turns(g),
        }

        operator = mutation_map.get(chosen)
        if operator:
            if asyncio.iscoroutinefunction(operator):
                mutated = await operator(genome)
            else:
                mutated = operator(genome)
            return mutated.to_dict()

        return genome_dict

    def _validate_offspring(self, offspring: list[Individual]) -> list[Individual]:
        """Valide et corrige les offspring."""
        valid = []
        for ind in offspring:
            genome = WorkflowGenome.from_dict(ind.genome)
            result = self.validator.validate(genome)

            if result.is_valid or result.auto_fixed:
                ind.genome = genome.to_dict()
                valid.append(ind)
            else:
                logger.warning(
                    f"Individu {ind.id} invalide : {result.errors}"
                )
        return valid

    def _get_phase_config(self) -> dict:
        """Retourne la configuration pour la phase courante."""
        if self.current_phase == "exploration":
            return {
                "mutation_rate": self.config.exploration_mutation_rate,
                "crossover_rate": self.config.exploration_crossover_rate,
                "elite_ratio": self.config.exploration_elite_ratio,
                "tournament_size": self.config.exploration_tournament_size,
                "mutations": self.config.exploration_mutations,
            }
        else:
            return {
                "mutation_rate": self.config.optimization_mutation_rate,
                "crossover_rate": self.config.optimization_crossover_rate,
                "elite_ratio": self.config.optimization_elite_ratio,
                "tournament_size": self.config.optimization_tournament_size,
                "mutations": self.config.optimization_mutations,
            }

    def _compute_scalar_fitness(self, scores_19d: list[float]) -> float:
        """Agrège le vecteur 19D en fitness scalaire.

        Pondération :
        - Critères MICRO (12) : poids total 40%
        - Critères MÉSO (5) : poids total 35%
        - Critères MACRO (2) : poids total 25%
        """
        weights = (
            [0.40 / 12] * 12 +  # MICRO
            [0.35 / 5] * 5 +    # MÉSO
            [0.25 / 2] * 2      # MACRO
        )
        return float(np.dot(scores_19d, weights))
```

### 4.4 Format de Sérialisation du Génome

Le génome est sérialisé en JSON pour la persistance et en YAML pour la lisibilité humaine.

**Exemple de génome JSON complet :**

```json
{
  "id": "wf-a3b2c1d4-e5f6-7890-abcd-ef1234567890",
  "generation": 42,
  "parent_ids": ["wf-parent1-uuid", "wf-parent2-uuid"],
  "mutation_history": ["crossover_swap_agents", "mutate_prompt_paraphrase"],

  "supervisor": {
    "id": "sup-001",
    "role": "supervisor",
    "system_prompt": "Tu es un coordinateur pédagogique expert...",
    "tool_ids": ["search_course", "get_definition", "get_examples"],
    "model": "sonnet",
    "temperature": 0.6,
    "max_tokens": 4096
  },

  "sub_agents": [
    {
      "id": "ag-researcher",
      "role": "researcher",
      "system_prompt": "Tu es un chercheur spécialisé...",
      "tool_ids": ["search_course", "get_definition"],
      "model": "haiku",
      "temperature": 0.3,
      "max_tokens": 2048
    },
    {
      "id": "ag-explainer",
      "role": "explainer",
      "system_prompt": "Tu es un pédagogue expert...",
      "tool_ids": ["get_examples", "get_related_concepts"],
      "model": "sonnet",
      "temperature": 0.7,
      "max_tokens": 3072
    }
  ],

  "tools": [
    {
      "name": "search_course",
      "description": "Recherche dans le contenu du cours les passages pertinents.",
      "schema": {"query": "string"},
      "enabled": true
    },
    {
      "name": "get_definition",
      "description": "Obtient la définition précise d'un terme du cours.",
      "schema": {"term": "string"},
      "enabled": true
    }
  ],

  "max_turns": 10,
  "delegation_strategy": "auto"
}
```

---

## 5. Estimation des Coûts

### 5.1 Modèle de Coût par Génération

**Hypothèses de base :**

| Paramètre | Valeur |
|-----------|--------|
| Taille population workflows | 50 individus |
| Queries par évaluation | 15 (10 gold + 5 adversarial) |
| Évaluateurs par individu | 5 |
| Tokens moyens par query d'exécution | ~2 000 input + ~1 000 output |
| Tokens moyens par évaluation | ~1 500 input + ~500 output |
| Tokens par mutation LLM-assistée | ~800 input + ~600 output |

**Calcul détaillé pour UNE génération :**

#### Phase d'Exécution (Pop. A)

```
50 individus x 15 queries = 750 exécutions de workflow

Chaque exécution (supervisor Sonnet + sub-agents Haiku) :
- Supervisor : ~2 000 tokens in + ~800 tokens out
- 2-3 sub-agents Haiku : ~3 000 tokens in + ~1 500 tokens out (total)
- Total par exécution : ~5 000 in + ~2 300 out

Coût par exécution :
- Supervisor (Sonnet 4.5) : 2 000 × $3/MTok + 800 × $15/MTok = $0.006 + $0.012 = $0.018
- Sub-agents (Haiku 4.5) : 3 000 × $1/MTok + 1 500 × $5/MTok = $0.003 + $0.0075 = $0.0105

Total par exécution : ~$0.029
Total exécution/génération : 750 × $0.029 = $21.75
```

#### Phase d'Évaluation (Pop. B)

```
750 résultats x 5 évaluateurs = 3 750 évaluations

Répartition :
- 60% via Batch API Haiku (critères micro) : 2 250 évals
- 40% via Batch API Sonnet (critères méso/macro) : 1 500 évals

Haiku Batch (50% réduction) :
  2 250 × (1 500 × $0.50/MTok + 500 × $2.50/MTok)
  = 2 250 × ($0.00075 + $0.00125)
  = 2 250 × $0.002 = $4.50

Sonnet Batch (50% réduction) :
  1 500 × (1 500 × $1.50/MTok + 500 × $7.50/MTok)
  = 1 500 × ($0.00225 + $0.00375)
  = 1 500 × $0.006 = $9.00

Total évaluation/génération : $4.50 + $9.00 = $13.50
```

#### Phase de Reproduction (Opérateurs Génétiques)

```
~25 crossovers + ~25 mutations par génération

Crossover LLM-assisté (50% des crossovers) :
  12 × (800 × $1/MTok + 600 × $5/MTok) = 12 × $0.0038 = $0.046

Mutations LLM-assistées (paraphrase, injection -- 40% des mutations) :
  10 × (800 × $1/MTok + 600 × $5/MTok) = 10 × $0.0038 = $0.038

Total reproduction/génération : ~$0.08
```

#### Calibration Ground Truth (1 fois sur 5)

```
Opus 4.6 sur les 10 meilleures réponses :
  10 × (3 000 × $5/MTok + 1 000 × $25/MTok) = 10 × $0.04 = $0.40
  Amorti sur 5 générations : $0.08/génération
```

### 5.2 Résumé des Coûts par Génération

| Composant | Coût/génération | % du total |
|-----------|----------------|------------|
| **Exécution workflows** | **$21.75** | **61.3%** |
| **Évaluation Batch** | **$13.50** | **38.1%** |
| Reproduction (opérateurs) | $0.08 | 0.2% |
| Calibration ground truth | $0.08 | 0.2% |
| **TOTAL** | **~$35.41** | **100%** |

### 5.3 Coût Total de l'Évolution

| Scénario | Générations | Coût estimé | Durée estimée |
|----------|-------------|-------------|---------------|
| **Minimal** (POC) | 20 | ~$708 | ~10h |
| **Standard** | 100 | ~$3 541 | ~50h |
| **Complet** (200 gén.) | 200 | ~$7 082 | ~100h |
| **Production** (avec optimisations) | 200 | ~$4 000-5 000 | ~60-80h |

### 5.4 Stratégies d'Optimisation des Coûts

**1. Prompt Caching (réduction estimée : 30-40%)**
```
Les system prompts des évaluateurs sont identiques pour toutes les évaluations
d'une même génération. Avec le cache 5min :
- 1ère éval : prix plein ($3/MTok pour Sonnet)
- Évals suivantes : cache read ($0.30/MTok) = 90% de réduction sur l'input
```

**2. Réduction de la taille de la population**
```
20 individus au lieu de 50 :
  → Exécution : 300 au lieu de 750 = $8.70
  → Évaluation : 1 500 au lieu de 3 750 = $5.40
  → Total : ~$14.18/génération (-60%)
```

**3. Évaluation partielle (échantillonnage)**
```
Évaluer chaque individu sur 5 queries au lieu de 15 :
  → Exécution : 250 au lieu de 750 = $7.25
  → Réduction de 67% sur l'exécution
```

**4. Stratégie "Haiku first" pour l'exécution**
```
Utiliser Haiku pour le supervisor aussi (au lieu de Sonnet) :
  Coût par exécution : 5 000 × $1/MTok + 2 300 × $5/MTok = $0.0165
  Total : 750 × $0.0165 = $12.38 (-43% sur l'exécution)

  Risque : qualité moindre de l'orchestration
  Mitigation : passer à Sonnet uniquement pour le top-25%
```

**5. Utilisation maximale du Batch API**
```
Regrouper TOUTES les évaluations (pas juste les micro) en Batch :
  → 50% de réduction sur la totalité
  → Latence acceptable si on batch par génération
```

### 5.5 Tableau Comparatif des Scénarios de Coût

| Scénario | Pop. | Queries | Gén. | Coût/gén. | Coût total | Durée |
|----------|------|---------|------|-----------|------------|-------|
| **Ultra-léger** (debug) | 10 | 5 | 10 | ~$3 | ~$30 | ~1h |
| **Léger** (validation) | 20 | 10 | 50 | ~$14 | ~$700 | ~15h |
| **Standard** | 50 | 15 | 100 | ~$35 | ~$3 500 | ~50h |
| **Standard + cache** | 50 | 15 | 100 | ~$22 | ~$2 200 | ~50h |
| **Complet** | 50 | 15 | 200 | ~$35 | ~$7 000 | ~100h |
| **Complet + toutes optims** | 50 | 15 | 200 | ~$18 | ~$3 600 | ~80h |

---

## Annexes

### A. Dépendances Python

```toml
# pyproject.toml
[project]
name = "eduflow-evolution"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "claude-agent-sdk>=0.10.0",
    "anthropic>=0.50.0",
    "numpy>=1.26.0",
    "scipy>=1.12.0",
    "aiosqlite>=0.20.0",
    "aiofiles>=24.1.0",
    "pyyaml>=6.0.0",
    "rich>=13.0.0",      # Terminal dashboard
    "pydantic>=2.5.0",   # Validation des schémas
    "tenacity>=8.2.0",   # Retry avec backoff
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
]
```

### B. Références

- **EvoPrompt** : Guo et al., "Connecting Large Language Models with Evolutionary Algorithms Yields Powerful Prompt Optimizers", ICLR 2024. [arXiv:2309.08532](https://arxiv.org/abs/2309.08532)
- **GAAPO** : "Genetic Algorithmic Applied to Prompt Optimization", Frontiers in AI, 2025. [DOI](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1613007/full)
- **Claude Agent SDK** : [Documentation officielle](https://platform.claude.com/docs/en/agent-sdk/overview) | [GitHub](https://github.com/anthropics/claude-agent-sdk-python)
- **Tarification Anthropic** : [Pricing](https://platform.claude.com/docs/en/about-claude/pricing) (février 2026)
- **LangGraph** : [Documentation](https://python.langchain.com/docs/langgraph)
- **Comparatif frameworks** : [o-mega.ai](https://o-mega.ai/articles/langgraph-vs-crewai-vs-autogen-top-10-agent-frameworks-2026)
