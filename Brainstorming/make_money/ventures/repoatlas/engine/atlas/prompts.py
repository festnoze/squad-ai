"""All agent prompts, verbatim contracts. Facts in, interpretation out.

Rules baked into every prompt:
- the agent may only restate or interpret facts present in its input
- uncertainty goes to open_questions, never into confident prose
- every path it emits must come from the input
- never use the em-dash character; use "-" or parentheses
"""

STACK_HINTS = {
    "python": (
        "Python codebase. Pay attention to: web framework (FastAPI/Flask/"
        "Django visible in routes and deps), ORM usage, settings/config "
        "modules, celery or background jobs, entry points (__main__, "
        "manage.py, app factories)."),
    "csharp": (
        ".NET codebase. Pay attention to: ASP.NET controllers and their "
        "routes, dependency injection registrations (Program.cs/Startup.cs), "
        "Entity Framework DbContext and entities, solution structure "
        "(projects = deployment units), async patterns."),
    "react": (
        "React frontend. Pay attention to: routing structure, state "
        "management (context/redux/query libraries in deps), API client "
        "layer (fetch/axios wrappers), component hierarchy (pages vs shared "
        "components), build tooling."),
    "angular": (
        "Angular frontend. Pay attention to: NgModules vs standalone "
        "components, routing modules and lazy loading, services and their "
        "injection scope, interceptors and guards, RxJS usage patterns."),
    "node": (
        "Node/TypeScript codebase. Pay attention to: express/nest routes, "
        "entry scripts in package.json, shared libraries."),
}

MODULE_READER = """You are documenting the module "{module}" of a legacy codebase
({stacks} stack). Everything below was extracted deterministically from the
code; it is your only ground truth.

{stack_hints}

Module metrics: {metrics}
Symbols found by scanners (name, kind, file, line):
{symbols}
HTTP/UI routes in this module:
{routes}
Imports from this module to others: {internal_deps}
Git signals: {git}
Source excerpts (truncated):
{excerpts}

Extract facts ONLY. If unsure, use open_questions instead of asserting.
Reply with ONLY a JSON object:
{{
 "module": "{module}",
 "purpose": "<2-3 sentences: what this module does for the product>",
 "entry_points": [{{"file": "<path>", "symbol": "<name>", "role": "<one line>"}}],
 "public_api": [{{"symbol": "<name>", "kind": "<class|function|endpoint|component>",
                 "file": "<path>", "summary": "<one line>"}}],
 "data": [{{"what": "<entity/table/store>", "where": "<path>", "note": "<one line>"}}],
 "risks": [{{"claim": "<specific risk>", "evidence": "<path and why>"}}],
 "key_files": [{{"path": "<path>", "role": "<one line>"}}],
 "open_questions": ["<needs a human answer>"]
}}
Every "file"/"path"/"where" value MUST appear in the input above.
Never use the em-dash character; use "-" or parentheses."""

WRITER_PREAMBLE = """You write documentation for paying clients. Input is verified
JSON extracted from their codebase; you may not invent anything not present
in the input. Write in {language}. Confident, plain prose. No filler, no
hedging: anything uncertain goes under a final "Open questions" heading.
Cite file paths in backticks. Diagrams in mermaid fenced blocks.
Never use the em-dash character; use "-" or parentheses.
"""

DOC_PROMPTS = {
    "01_overview.md": """{preamble}
Repo: {repo} ({stacks}). Meters: {meters}
Module summaries:
{modules_json}
Declared dependencies (top 30): {deps}
Write 01_overview.md: what the system does, its tech stack, how it is run,
and its main entry points. One page. Return ONLY the markdown.""",

    "02_architecture.md": """{preamble}
Module summaries:
{modules_json}
Module dependency edges: {edges}
Write 02_architecture.md: the system's components and how data/requests flow
through them. Include one mermaid component diagram built from the edges
above, and a "Boundaries and contracts" section listing the interfaces
between modules. Return ONLY the markdown.""",

    "07_onboarding.md": """{preamble}
Repo: {repo} ({stacks}). Manifest facts: {manifests}
Module summaries:
{modules_json}
Hotspots (change with care): {hotspots}
Write 07_onboarding.md: a new developer's first week. Environment setup
derived from the manifest facts only, how to run and test, a code tour in
reading order (start with the most central module), and one suggested first
safe change referencing a real low-risk file from the input.
Return ONLY the markdown.""",

    "08_debt_register.md": """{preamble}
Risks extracted per module:
{risks_json}
Hotspots (churn x size, bus factor): {hotspots}
Scanner notes (parse failures, oddities): {notes}
Write 08_debt_register.md: a ranked debt register. Each item: P1/P2/P3,
the claim, its evidence path, and what addressing it would take. Carry the
evidence paths through unchanged. Return ONLY the markdown.""",
}

MODULE_DOC = """{preamble}
Write the documentation page for module "{module}". Verified summary:
{summary_json}
Git signals: {git}
Structure: purpose, how it connects to the rest (its imports/importers),
public API table, data it owns, risks, key files table, open questions.
Return ONLY the markdown."""

FACT_CHECK = """You are auditing a documentation claim against source code.
Claim: "{claim}" (from {doc}).
Relevant source excerpt:
{excerpt}
Reply ONLY with JSON: {{"verdict": "supported|unsupported|unclear",
"reason": "<one line>"}}"""

MAPPER_REFINE = """These modules were detected heuristically in a {stacks} repo:
{modules_json}
Propose better human-readable names and any merges of fragments that a
developer would consider one unit. Reply ONLY with a JSON array:
[{{"name": "<kebab-case>", "merge_of": ["<existing name>", ...]}}]
Keep between 5 and {max_modules} modules. Do not invent modules."""
