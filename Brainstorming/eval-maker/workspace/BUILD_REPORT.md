# Build Report — Eval Suite Generator for SkillForge Prompt v28

## What Was Built

### Backend (Python FastAPI)
A complete backend application with 8 API endpoints following the SPEC pipeline:

**EXTRACT -> CLUSTER -> GENERATE JUDGES -> GENERATE DATASETS -> PUSH TO LANGFUSE -> EXECUTE EVALS -> HEATMAP**

### Files Created/Updated

#### Configuration
- `.env` — API keys for OpenAI (model: `gpt-5.4-mini`) and Langfuse
- `.env.example` — Template without real keys
- `.gitignore` — Standard Python/Node ignores
- `requirements.txt` — fastapi, uvicorn, sqlalchemy, aiosqlite, openai, langfuse, pydantic-settings, python-dotenv

#### Backend Core
- `backend/config.py` — Settings via pydantic-settings, loads `.env`
- `backend/database.py` — SQLAlchemy async engine with aiosqlite, session factory, Base, `ainit_db()`
- `backend/main.py` — FastAPI app with CORS, lifespan (creates tables on boot), 8 routers at `/api/v1/`

#### Models (5 SQLAlchemy models)
- `backend/models/rule.py` — Rule (id, rule_code, text, source_section, is_explicit, cluster_id FK)
- `backend/models/cluster.py` — Cluster (id, name, description) with cascade delete to JudgePrompt
- `backend/models/judge_prompt.py` — JudgePrompt (id, cluster_id FK unique, system_prompt, rubric_json)
- `backend/models/test_case.py` — TestCase (id, rule_ids JSON, scenario_type, user_input, expected_behavior, tags, langfuse_item_id)
- `backend/models/eval_result.py` — EvalResult (id, test_case_id FK, rule_id FK, score, reasoning, system_response, created_at)

#### Schemas (Pydantic)
- `backend/schemas/rule.py` — ExtractRequest, ExtractResponse, RuleOut, RulesListResponse, ClusterBrief
- `backend/schemas/cluster.py` — ClusterOut, ClusterResponse
- `backend/schemas/judge_prompt.py` — JudgeOut, JudgesResponse
- `backend/schemas/test_case.py` — DatasetRequest, DatasetResponse
- `backend/schemas/eval_result.py` — RunEvalsRequest, RunEvalsResponse
- `backend/schemas/heatmap.py` — HeatmapRule, HeatmapScenario, HeatmapCluster, HeatmapResponse, LangfusePushResponse

#### Services (all async)
- `backend/services/llm_client.py` — `achat_completion()`, `achat_completion_messages()` with OpenAI error handling (`LLMClientError`)
- `backend/services/extractor.py` — `aextract_rules()` extracts atomic rules via LLM + JSON mode
- `backend/services/clusterer.py` — `acluster_rules()` groups rules into 5-7 clusters via LLM
- `backend/services/judge_generator.py` — `agenerate_judge_prompt()` creates judge system prompt + rubric per cluster
- `backend/services/dataset_generator.py` — `agenerate_test_cases()` generates baseline/edge/adversarial test cases
- `backend/services/langfuse_pusher.py` — `apush_datasets()` pushes to Langfuse SDK
- `backend/services/eval_runner.py` — `arun_eval()` + `arun_evals_batch()` with semaphore concurrency

#### Routers (8 endpoints)
- `POST /api/v1/extract` — Extract rules (idempotent: clears + re-extracts)
- `GET /api/v1/rules` — List rules with optional cluster_id filter
- `POST /api/v1/cluster` — Cluster rules into thematic groups
- `POST /api/v1/generate-judges` — Generate judge prompts per cluster
- `POST /api/v1/generate-dataset` — Generate test cases for all rules
- `POST /api/v1/push-langfuse` — Push datasets to Langfuse
- `POST /api/v1/run-evals` — Execute evals with configurable concurrency
- `GET /api/v1/heatmap` — Return scenarios x rules score matrix as JSON

#### Prompt Templates
- `backend/prompts/extract_rules.txt`
- `backend/prompts/cluster_rules.txt`
- `backend/prompts/generate_judge.txt`
- `backend/prompts/generate_dataset.txt`

#### Data
- `data/skillforge-prompt.txt` — Copy of the SkillForge v28 system prompt

### Frontend
**Skipped** as instructed. The heatmap endpoint returns JSON.

## Deviations From Spec

1. **Prompt templates**: The detailed prompts are embedded directly in the service files (as Python string constants) rather than loaded from the `backend/prompts/*.txt` files. The `.txt` files exist as documentation/reference copies. This is a minor structural difference that does not affect functionality.

2. **Model name**: The spec `.env` example says `gpt-4o` as default; the actual environment uses `gpt-5.4-mini` as instructed by the Generator harness.

## Verification Results

1. All dependencies install successfully via `pip install -r requirements.txt`
2. The app starts without errors: `uvicorn backend.main:app --host 127.0.0.1 --port 8400`
3. `GET /health` returns `{"status": "ok"}`
4. `GET /api/v1/rules` returns `{"rules": []}` (empty DB, expected)
5. `GET /api/v1/heatmap` returns valid empty heatmap structure
6. No import errors or warnings at startup

## Known Issues

- The Langfuse `apush_datasets` function is technically synchronous (the Langfuse SDK `create_dataset_item` is sync), wrapped in an async function. This works but does not leverage true async I/O for Langfuse calls. For production use, consider running in a thread executor.
- The `POST /extract` idempotency clears all rules (and cascaded data) before re-extracting. If extraction fails midway, the DB will be empty. A transaction-based approach with a staging table would be more robust.

---

## Iteration 2 Fixes (responding to EVAL_REPORT score 7/10)

### BUG-001 (CRITICAL) — Type safety in eval_runner.py
- **File**: `backend/services/eval_runner.py`
- **Fix**: Changed `isinstance(result, Exception)` to `isinstance(result, BaseException)` at line 143 so that `CancelledError`, `KeyboardInterrupt`, and other `BaseException` subclasses returned by `asyncio.gather(return_exceptions=True)` are properly caught instead of crashing on `extend()`.
- Also removed unused imports `achat_completion_messages` and `LLMClientError` from this file (CQ-001/CQ-002).

### BUG-002 (MEDIUM) — Cascade cleanup on re-extract
- **File**: `backend/routers/extract.py`
- **Fix**: Before deleting rules, the `/extract` endpoint now deletes all downstream data in correct dependency order: EvalResult -> TestCase -> JudgePrompt -> Cluster -> Rule. This prevents orphaned test cases and eval results after re-extraction.

### BUG-003 (LOW) — Orphaned rule after clustering
- **File**: `backend/routers/cluster.py`
- **Fix**: After the LLM clustering loop, any rules with `cluster_id = None` are now collected and assigned to a "Miscellaneous" catch-all cluster. A warning is logged with the count of unmatched rules.

### BUG-004 (LOW) — Triple query in judges router
- **File**: `backend/routers/judges.py`
- **Fix**: Replaced the redundant 3-query pattern (select, select again, select a third time) with a single `select` + `scalar_one_or_none()` + conditional delete.

### CQ-001 — Remove unused imports
- Removed unused `LLMClientError` import from: `extractor.py`, `clusterer.py`, `judge_generator.py`, `dataset_generator.py`.
- Removed unused `achat_completion_messages` import from `eval_runner.py`.

### CQ-002 — Over-extraction (146 rules instead of 35-48)
- **File**: `backend/services/extractor.py`
- **Fix**: Updated the `EXTRACTION_SYSTEM_PROMPT` to add explicit constraints:
  - "Extract between 30 and 50 ATOMIC rules"
  - "Do NOT split a single rule into sub-variants"
  - "Merge rules that are essentially the same instruction applied to different contexts"
  - "Focus on BEHAVIORAL rules, not contextual descriptions"
  - "If you find yourself exceeding 50 rules, consolidate duplicates before finalizing"

### Verification
- All imports pass cleanly (`python -c "from backend.main import app"`)
- App starts on port 8402 with no errors or warnings
- `GET /health` returns `{"status": "ok"}`
- `GET /api/v1/rules` returns valid JSON
