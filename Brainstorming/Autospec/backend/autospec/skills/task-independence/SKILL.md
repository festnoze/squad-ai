---
name: task-independence
description: >
  Judge whether decomposed tasks can be built in parallel without conflicting on
  files, BEFORE the streams scheduler runs them. Use after a story is decomposed
  into tasks and before parallel build: it certifies file-disjoint tasks as
  parallelizable and serializes (or merges) the rest. Pairs with the
  deterministic analyzer `orchestrator/independence.py`, which is the safety
  floor — this skill only adds constraints, never removes a required one.
  Triggers: "parallel", "independence", "conflit de merge", "same file",
  "decompose", "scheduling", "file_globs", "serialize tasks".
type: domain
enforcement: required_when_applicable
priority: critical
---

# Task Independence Judge

## Why this exists

Autospec builds independent tasks in parallel, each in its own git worktree, then
merges them back. If two tasks edit the **same file** (e.g. two frontend tasks
both touching `App.tsx`), their worktrees conflict on merge and green work is
**lost**. This skill prevents that by certifying parallelism *before* the build.

## The two-layer contract

1. **Deterministic floor (`orchestrator/independence.py`)** — pure, no LLM. From
   each task's declared `file_globs`, it computes overlapping pairs and injects
   `depends_on` so they serialize. It is conservative: unproven disjointness ⇒
   assume overlap. **You cannot override this floor downward.**
2. **This skill (LLM judge)** — refines on top: completes missing claims, decides
   genuine independence vs. hidden coupling, and may *add* ordering or *merge*
   tasks. You only ever make the schedule **safer**, never riskier.

## When to use

- Right after a US is decomposed into tasks, before `_abuild_phase_streams`.
- When tasks share a `stream` / `file_root` and the analyzer flags a conflict.
- When a task has **no** `file_globs` (it will otherwise be serialized wholesale).

## Procedure

1. **Read the claims.** For each task collect `id`, `stream`, `file_globs`,
   `depends_on`, and its title/description.
2. **Complete claims.** If a task omits `file_globs`, infer them from its intent
   (a component task → `frontend/src/components/Foo.tsx`; an endpoint task →
   `backend/<pkg>/api/router.py`). Never leave a frontend task claiming the whole
   `App.tsx` unless it really rewrites it — split or scope it.
3. **Atomize.** Prefer many small file-scoped tasks over few broad ones. If two
   responsibilities sit in one task touching disjoint files, suggest a split.
4. **Judge each flagged pair** (from the analyzer):
   - `independent` — globs truly disjoint after your completion → may parallelize.
   - `add_dependency: a -> b` — they share a file; serialize (later waits earlier).
   - `merge: [a, b]` — they are one inseparable unit (same file, same change).
5. **Default to serialize** whenever uncertain. Parallelism is a bonus.

## Output (single bounded JSON object)

```json
{
  "claims": { "T-3-fe": ["frontend/src/components/TodoItem.tsx"],
              "T-4-fe": ["frontend/src/components/TodoList.tsx"] },
  "verdicts": [
    { "pair": ["T-3-fe", "T-4-fe"], "decision": "independent" },
    { "pair": ["T-3-fe", "T-5-fe"], "decision": "add_dependency",
      "order": ["T-5-fe", "T-3-fe"], "reason": "both edit App.tsx routing" }
  ],
  "merges": [],
  "notes": "T-9-fe left whole-App; scoped to src/App.tsx integration only."
}
```

## Hard rules

- Two tasks may be `independent` **only** if their (completed) `file_globs` are
  disjoint. If they overlap, you must `add_dependency` or `merge`.
- Cross-stream tasks (different `file_root`) are independent by construction —
  do not serialize a `frontend` task against a `backend` task on file grounds
  (only functional `depends_on`, e.g. the UI needs the API, applies there).
- Never introduce a cycle. Order by existing functional dependency, else by
  declaration order.
- Your decisions are advisory **upward only**: the deterministic floor still
  serializes any real overlap you missed.
