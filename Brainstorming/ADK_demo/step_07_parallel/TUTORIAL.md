# Step 6 - ParallelAgent (Execution concurrente)

## Concepts

### ParallelAgent
Execute tous ses sub-agents **en meme temps**. Parfait quand les taches sont independantes.

```python
from google.adk.agents import ParallelAgent

parallel = ParallelAgent(
    name="parallel_tasks",
    sub_agents=[agent_a, agent_b, agent_c],  # Lancees en parallele
)
```

### Pas de partage de state entre branches
Point critique : pendant l'execution parallele, les branches **ne voient PAS** les modifications de state des autres. Chaque branche lit le state tel qu'il etait au demarrage du ParallelAgent. Les `output_key` sont merges apres que toutes les branches sont terminees.

### Pattern classique : Sequential + Parallel
On imbrique souvent les workflow agents :

```
SequentialAgent
  ├── Writer (ecrit le code)
  ├── ParallelAgent
  │     ├── SecurityReviewer (output_key="security_review")
  │     ├── PerfReviewer (output_key="perf_review")
  │     └── StyleReviewer (output_key="style_review")
  └── Synthesizer (lit les 3 reviews depuis le state)
```

### Nesting de workflow agents
Les workflow agents se combinent librement :
- `SequentialAgent` peut contenir des `ParallelAgent`
- `ParallelAgent` peut contenir des `SequentialAgent`
- Pas de limite de profondeur

## Diagramme

```
        reviewed_code_pipeline (SequentialAgent)
 ┌──────────────────────────────────────────────────────────┐
 │                                                          │
 │  ┌────────┐                                              │
 │  │ Writer │──output_key──> state["generated_code"]       │
 │  └────────┘                       │                      │
 │                                   ▼                      │
 │              ┌─── parallel_review (ParallelAgent) ───┐   │
 │              │                                       │   │
 │              │  ┌──────────────┐  state["security"]  │   │
 │              │  │  Security    │──────────────────>   │   │
 │              │  └──────────────┘                      │   │
 │              │  ┌──────────────┐  state["perf"]      │   │
 │              │  │ Performance  │──────────────────>   │   │
 │              │  └──────────────┘                      │   │
 │              │  ┌──────────────┐  state["style"]     │   │
 │              │  │    Style     │──────────────────>   │   │
 │              │  └──────────────┘                      │   │
 │              └───────────────────────────────────────┘   │
 │                                   │                      │
 │                                   ▼                      │
 │              ┌──────────────┐                            │
 │              │ Synthesizer  │ lit les 3 reviews          │
 │              │              │──> score + verdict          │
 │              └──────────────┘                            │
 └──────────────────────────────────────────────────────────┘
```

## Exploration

Ouvre [agent.py](agent.py) et observe :
1. Les 3 reviewers paralleles avec chacun son `output_key`
2. Le `ParallelAgent` qui les regroupe
3. Le `synthesizer_agent` qui lit `{security_review}`, `{performance_review}`, `{style_review}`
4. Le `SequentialAgent` racine qui imbrique tout : writer -> parallel -> synthesizer

## Prompts de test

Lance `adk web` -> `step_06_parallel` :

| Prompt | Resultat attendu | Quoi observer |
|--------|-----------------|---------------|
| "Write a function to transfer money between accounts" | Code + 3 reviews + synthese finale | Dans Events : les 3 reviewers apparaissent quasi-simultanement |
| "Write a hello world function" | Meme pipeline, reviews plus courtes | Security devrait trouver moins de problemes |

**Point cle** : les 3 reviewers ne voient PAS les resultats des autres pendant l'execution. Ils lisent tous le meme state initial.

## Exercice

**Mission** : Creer un systeme de traduction parallele.

Ouvre `exercise_06/agent.py` et complete les `# TODO`.

Pipeline :
1. `TextAnalyzer` : analyse le texte source (tool `analyze_text`), `output_key="analysis"`
2. `ParallelAgent` avec 3 traducteurs :
   - `FrenchTranslator` -> `output_key="french_translation"`
   - `SpanishTranslator` -> `output_key="spanish_translation"`
   - `JapaneseTranslator` -> `output_key="japanese_translation"`
3. `TranslationMerger` : combine les 3 traductions dans un rapport final

Le tout dans un `SequentialAgent` : Analyzer -> ParallelTranslators -> Merger

Teste : "Translate 'The quick brown fox jumps over the lazy dog'"

## Quiz

Teste tes connaissances : ouvre [quiz/index.html](../quiz/index.html) dans ton navigateur et selectionne **Step 7**.
