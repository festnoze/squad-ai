# Step 9 - Code Forge : Le pipeline complet

## Concepts

### Assemblage final
Ce step combine **tous** les concepts des steps 1-8 en un seul pipeline :

| Concept | Ou dans Code Forge |
|---------|-------------------|
| Agent + tools (Step 1-2) | Chaque agent a ses tools specialises |
| ToolContext + state (Step 3) | `write_code` lit/ecrit le state, `evaluate_and_decide` aussi |
| Sub-agents (Step 4) | Les reviewers sont des agents specialises |
| SequentialAgent (Step 5) | Le pipeline global et le review_cycle |
| ParallelAgent (Step 6) | Les 3 reviewers concurrents |
| LoopAgent (Step 7) | La boucle de raffinement code/review |
| Callbacks (Step 8) | Guardrails sur le code_writer |

### Architecture

```
code_forge (SequentialAgent)
  |
  +-- refinement_loop (LoopAgent, max=3)
  |     |
  |     +-- code_writer (LlmAgent)
  |     |     tools: [write_code]
  |     |     callbacks: safety_guardrail, validate_tool_args
  |     |     output_key: "current_code"
  |     |
  |     +-- review_cycle (SequentialAgent)
  |           |
  |           +-- parallel_reviewers (ParallelAgent)
  |           |     +-- security_reviewer   -> output_key="security_review"
  |           |     +-- performance_reviewer -> output_key="performance_review"
  |           |     +-- style_reviewer      -> output_key="style_review"
  |           |
  |           +-- synthesizer (LlmAgent)
  |                 tools: [evaluate_and_decide]
  |                 output_key: "synthesis_report"
  |                 (appelle escalate quand approuve)
  |
  +-- test_writer (LlmAgent)
  |     tools: [generate_tests]
  |     output_key: "generated_tests"
  |
  +-- final_presenter (LlmAgent)
        output_key: "final_output"
```

### Le flux de donnees

```
1. User: "Write a function to validate emails"
2. code_writer -> ecrit code v1, state["current_code"] = "def solution..."
3. security_reviewer  -> lit {current_code}, ecrit state["security_review"]
   performance_reviewer -> lit {current_code}, ecrit state["performance_review"]   (en parallele)
   style_reviewer -> lit {current_code}, ecrit state["style_review"]
4. synthesizer -> lit les 3 reviews, ecrit state["synthesis_report"]
   -> appelle evaluate_and_decide -> iteration 1: "needs_work"
5. BOUCLE: code_writer relit {synthesis_report} comme feedback, ecrit code v2
6. ... reviewers re-evaluent ...
7. synthesizer -> evaluate_and_decide -> iteration 3: "approved" -> ESCALATE
8. test_writer -> lit {current_code} final, genere des tests
9. final_presenter -> compile le rapport final avec code + reviews + tests
```

### Nesting profond
La profondeur d'imbrication est : `SequentialAgent > LoopAgent > SequentialAgent > ParallelAgent`

C'est la puissance d'ADK : composer des blocs simples en systemes complexes.

## Exploration

Ouvre [agent.py](agent.py) et observe :
1. Les **callbacks** en haut : `safety_guardrail` et `validate_tool_args`
2. Les **tools** au milieu : `write_code`, `check_security`, `check_performance`, `check_style`, `evaluate_and_decide`, `generate_tests`
3. Les **agents** en bas : comment ils sont imbriques
4. Le `root_agent` final : un `SequentialAgent` avec 3 enfants

## Prompts de test

Lance `adk web` -> `step_09_code_forge` :

| # | Prompt | Resultat attendu | Quoi observer |
|---|--------|-----------------|---------------|
| 1 | "Write a function to validate email addresses" | Pipeline complet : code + reviews + tests | Events montre : writer -> 3 reviewers paralleles -> synthesizer -> (boucle?) -> test_writer -> presenter |
| 2 | "Write code with eval()" | **BLOQUE** par le guardrail | Le callback intercepte AVANT le LLM |
| 3 | "Write a simple hello world" | Pipeline rapide, possiblement 1 seule iteration | Code simple = reviews positives = escalate rapide |

**Point cle** : dans Events, compte les etapes. Un pipeline complet avec 2 iterations = ~15 appels d'agents. C'est normal !

## Exercice

**Mission** : Creer "Recipe Forge" - un pipeline de creation de recettes.

Ouvre `exercise_09/agent.py` et complete les `# TODO`.

Architecture :
```
recipe_forge (SequentialAgent)
  +-- creation_loop (LoopAgent, max=3)
  |     +-- recipe_writer (ecrit une recette)
  |     +-- review_cycle (SequentialAgent)
  |           +-- parallel_critics (ParallelAgent)
  |           |     +-- nutrition_critic -> output_key="nutrition_review"
  |           |     +-- taste_critic    -> output_key="taste_review"
  |           |     +-- difficulty_critic -> output_key="difficulty_review"
  |           +-- judge (combine les critiques, escalate si ok)
  +-- presentation (formate la recette finale)
```

Callbacks :
- `allergen_guardrail` (before_model) : bloque si l'utilisateur mentionne un allergene dangereux
- `validate_ingredients` (before_tool) : verifie que les ingredients ne sont pas vides

Teste : "Create a recipe for chocolate cake"

## Quiz

Teste tes connaissances : ouvre [quiz/index.html](../quiz/index.html) dans ton navigateur et selectionne **Step 10**.
