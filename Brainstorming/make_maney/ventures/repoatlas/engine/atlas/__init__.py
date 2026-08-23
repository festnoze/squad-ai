"""RepoAtlas engine: reverse-engineer codebases into a verified fact graph,
then render understanding (surveys, documentation packs) from it.

Design rule: deterministic scanners extract facts; agents only interpret
them. The pipeline is fully functional without an LLM (facts-only packs);
LLM enrichment is layered on top when the claude CLI is available.
"""

__version__ = "0.1.0"
