# dspyer

Prompt & model optimization API. Give it a **Langfuse prompt**, a **Langfuse dataset** and a set of **evaluators**; it runs an improvement loop using several optimization methods and benchmarks candidate models, then returns (and optionally pushes back to Langfuse) the best-scoring prompt/model pair.

## Optimization methods

| Method | What it does |
|---|---|
| `opro` | OPRO-style meta-prompting: an optimizer LLM sees the score trajectory + worst failures and proposes improved prompts |
| `cod` | Chain-of-Density refinement: sequential passes that fold missing constraints into the prompt without bloating it |
| `fewshot` | Injects worked examples from the train split (easiest + hardest items) as demos |
| `dspy` | DSPy `BootstrapFewShot` compilation; the compiled instructions + demos are flattened back to a plain prompt |

## Evaluators

`exact_match`, `contains`, `regex` (with `pattern`), `json_valid`, `similarity` (difflib ratio), `llm_judge` (with `criteria` + optional `judge_model`), `langfuse` (fetches an evaluator template from Langfuse by `name` and runs it as an LLM judge). Each accepts a `weight`.

## How the loop works

1. Fetch prompt (by name + label/version) and dataset items from Langfuse; split train/val.
2. Baseline evaluation of the current prompt on the task model.
3. Each round, every requested method proposes candidates → candidates scored on **train** → best promoted to **val** → accepted only if it beats the current best (guards against overfitting).
4. Model-selection loop: the best prompt is benchmarked across `candidate_models`.
5. Optionally the winner is pushed to Langfuse as a new prompt version with your label, and the optimization gain is recorded as a Langfuse score.

## Setup

```powershell
uv sync --all-extras
copy .env.example .env   # fill in Langfuse + provider keys
```

## Run

```powershell
uv run dspyer-serve
# or
uv run uvicorn dspyer.main:app --host 127.0.0.1 --port 8200
```

OpenAPI docs: http://127.0.0.1:8200/docs

## API

```http
POST /optimizations            # start a job (202, returns job id)
GET  /optimizations            # list jobs
GET  /optimizations/{id}       # job status, progress log, result
GET  /optimizations/{id}/best-prompt
DELETE /optimizations/{id}     # cancel
GET  /methods                  # available methods & evaluator types
GET  /health
```

### Example request

```json
{
  "prompt_name": "support-answer",
  "prompt_label": "production",
  "dataset_name": "support-eval-set",
  "evaluators": [
    { "type": "similarity", "weight": 1 },
    { "type": "llm_judge", "criteria": "Answer is factually consistent with the expected output and polite.", "weight": 2 }
  ],
  "methods": ["opro", "cod", "fewshot", "dspy"],
  "task_model": "openai/gpt-4o-mini",
  "candidate_models": ["anthropic/claude-haiku-4-5-20251001", "openai/gpt-4o"],
  "rounds": 3,
  "candidates_per_method": 2,
  "max_items": 40,
  "push_best_to_langfuse": true,
  "push_label": "optimized"
}
```

## Tests

```powershell
uv run pytest
```

Tests run fully offline (fake LLM + fake Langfuse).
