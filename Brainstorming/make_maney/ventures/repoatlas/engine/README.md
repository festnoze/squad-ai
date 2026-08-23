# RepoAtlas engine

The reverse-engineering system behind the RepoAtlas platform (stages 1-3:
Measure, Understand, Shield targeting). It scans one repo or a whole
multi-repo estate and turns it into verified understanding: meters, an
estate triage, a fact graph, and a documentation pack that passes machine
verification before anyone reads it.

Pure Python 3.11+ stdlib. First-class stacks: **Python** (AST-exact),
**C#/ASP.NET**, **React**, **Angular** (documented heuristics). Anything
else still gets inventoried and metered.

## The design rule

**Deterministic scanners extract facts; agents only interpret them.**

- Scanners produce symbols, routes, imports, and dependencies with file/line
  evidence. Same commit in, same facts out.
- Git analysis produces churn, bus factor, and hotspots. Numbers, not vibes.
- The LLM layer (headless `claude -p`) receives ONLY those facts plus
  bounded source excerpts, and everything it writes goes through gates.
- With no `claude` CLI (or `--no-llm`), the pipeline still delivers a
  complete facts-only pack: tables instead of prose, stamped as such.

## Usage

```bash
cd engine
python -m unittest                     # 27 tests

python run_atlas.py intake --config atlas.json    # meters (pricing basis)
python run_atlas.py survey --config atlas.json    # estate triage + quotes
python run_atlas.py pack   --config atlas.json [--repo NAME] [--no-llm]
python run_atlas.py diff   --config atlas.json --repo NAME   # drift
```

Config: see `examples/atlas.example.json` (name, repos with paths, llm
on/off, exclusions). Outputs land in the configured `out` dir:
`survey.md`/`survey.json`, and per repo `pack/` plus
`work/<repo>/snapshots/*.json` (the fact graph, diffable across runs).

## Pipeline anatomy

```
intake.py         walk + classify + count (vendored/generated excluded)
scanners/         python_scanner (ast), csharp_scanner, js_scanner (react+angular)
gitstats.py       churn, authorship, bus factor, hotspots (subtree-aware)
mapping.py        module detection + import-derived module dependency edges
estate.py         multi-repo survey: identities, coupling edges, triage
                  thresholds (documented in code), pack quotes per PRD meters
factgraph.py      evidence-carrying facts, JSON snapshots, diff = drift
readers.py        per-module digests (capped) -> LLM summaries -> facts
synthesis.py      the pack: overview, architecture (mermaid), module docs,
                  dependencies, onboarding, debt register; facts-only fallback
verify.py         gates: G1 cited paths exist (100%), G2 symbols found (98%),
                  G3 structure complete; verification_report.md ships in-pack
claude_client.py  headless claude wrapper: stdin prompt, JSON extraction,
                  full prompt/response logs under work/<repo>/logs
prompts.py        all agent prompts + per-stack reading hints
```

## Scaling to estates

- The survey is metadata-level: it runs on dozens of repos in minutes and
  produces the triage (deep / docs-only / inventory) plus coupling edges
  from identity matching (package names, assemblies, namespaces; generic
  names like "tests" are blacklisted to avoid false edges).
- Deep packs run per repo; module digests are size-capped, so LLM cost
  scales with module count, not LOC.
- Runtime coupling (HTTP calls between services) is NOT detected yet; the
  survey says so explicitly rather than pretending.

## Adding a stack

1. Subclass `Scanner` in `atlas/scanners/`, declare `extensions`, implement
   `scan_file` (and `scan_manifests` for dependency files). Emit only facts
   a heuristic can defend; put doubts in `notes`.
2. Register it in `scanners/__init__.py`.
3. Add a fixture repo under `tests/fixtures/` and assertions in
   `tests/test_scanners.py` (symbols, routes, deps).
4. Add a reading hint in `prompts.STACK_HINTS`.

## Honest limitations (v0.1)

- C#/JS scanners are regex heuristics: good for inventory and routing
  surface, not for full call graphs. Roslyn/tree-sitter integration is the
  upgrade path when an engagement justifies it.
- Complexity is proxied by size and churn, not cyclomatic measurement.
- LLM-mode claim spot-checking (gate G4 in the PRD) has its prompt in
  prompts.py but is not yet wired into run_gates.
- The pack ships as markdown; the self-contained HTML site renderer from
  PRD.md is not built yet.
