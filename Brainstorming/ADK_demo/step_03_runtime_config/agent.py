"""Step 3 - Runtime, Configuration et Donnees avancees.

Concepts: Runner (execution programmatique), generate_content_config,
          output_schema (Pydantic), Artifacts, Memory (MemoryService).

Try in adk web:
  - "Analyze the code: def fib(n): return n if n<2 else fib(n-1)+fib(n-2)"
  - "Save this report as an artifact"
  - "What did we discuss in previous sessions?"
"""

from google.adk.agents import Agent
from google.adk.tools import load_memory
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from pydantic import BaseModel, Field


# ============================================================
# 1. generate_content_config : controle du LLM
# ============================================================
# temperature=0.2 -> reponses precises et reproductibles
# temperature=0.9 -> reponses creatives et variees
# max_output_tokens -> limite la longueur de la reponse

PRECISE_CONFIG = types.GenerateContentConfig(
    temperature=0.2,
    max_output_tokens=500,
)

CREATIVE_CONFIG = types.GenerateContentConfig(
    temperature=0.9,
    max_output_tokens=1000,
)


# ============================================================
# 2. output_schema : forcer une reponse JSON structuree
# ============================================================

class CodeAnalysis(BaseModel):
    """Schema Pydantic pour structurer la reponse du LLM."""
    language: str = Field(description="Programming language detected")
    complexity: str = Field(description="Complexity level: simple, moderate, complex")
    summary: str = Field(description="One-line summary of what the code does")
    issues: list[str] = Field(description="List of potential issues found")
    score: int = Field(description="Quality score from 1 to 10")


# ============================================================
# 3. Artifacts : sauvegarder des fichiers binaires
# ============================================================

async def asave_report_artifact(report_text: str, filename: str, tool_context: ToolContext) -> dict:
    """Saves a text report as a persistent artifact file.

    Use this to save analysis reports that should persist beyond the session state.
    Artifacts are versioned - each save creates a new version.

    Args:
        report_text: The report content to save.
        filename: Name for the artifact file (e.g. "analysis_report.txt").

    Returns:
        Dictionary with save confirmation and version info.
    """
    artifact = types.Part.from_text(text=report_text)
    version = await tool_context.save_artifact(filename=filename, artifact=artifact)
    return {
        "status": "success",
        "message": f"Report saved as artifact '{filename}' (version {version})",
        "filename": filename,
        "version": version,
    }


async def aload_report_artifact(filename: str, tool_context: ToolContext) -> dict:
    """Loads a previously saved report artifact.

    Args:
        filename: Name of the artifact to load.

    Returns:
        Dictionary with the artifact content or error.
    """
    artifact = await tool_context.load_artifact(filename=filename)
    if artifact is None:
        return {"status": "error", "message": f"Artifact '{filename}' not found."}
    text = artifact.text if hasattr(artifact, "text") else str(artifact)
    return {
        "status": "success",
        "filename": filename,
        "content": text,
    }


async def alist_artifacts(tool_context: ToolContext) -> dict:
    """Lists all saved artifacts in the current session.

    Returns:
        Dictionary with list of artifact filenames.
    """
    files = await tool_context.list_artifacts()
    return {
        "status": "success",
        "artifacts": files if files else [],
        "count": len(files) if files else 0,
    }


# ============================================================
# 4. Memory : memoire cross-sessions (long terme)
# ============================================================
# load_memory est un tool built-in d'ADK qui cherche dans le MemoryService
# Il permet a l'agent de retrouver des infos de conversations passees


# ============================================================
# Agents avec differentes configurations
# ============================================================

# Agent avec reponse structuree (output_schema)
code_analyzer = Agent(
    name="code_analyzer",
    model="gemini-2.5-flash",
    description="Analyzes code and returns structured JSON analysis.",
    instruction=(
        "You are a code analyzer. When given code, analyze it thoroughly.\n"
        "Your response MUST follow the exact JSON schema provided.\n"
        "Be precise in your analysis."
    ),
    output_schema=CodeAnalysis,
    generate_content_config=PRECISE_CONFIG,
)

# Agent principal avec artifacts et memory
root_agent = Agent(
    name="smart_assistant",
    model="gemini-2.5-flash",
    description="An assistant with artifact storage and long-term memory.",
    instruction=(
        "You are a smart assistant with advanced capabilities:\n"
        "1. Save reports as artifacts using save_report_artifact\n"
        "2. Load previous reports using load_report_artifact\n"
        "3. List all saved artifacts using list_artifacts\n"
        "4. Search past conversations using load_memory\n\n"
        "When the user asks to save something, use artifacts.\n"
        "When the user asks about past conversations, use load_memory."
    ),
    tools=[asave_report_artifact, aload_report_artifact, alist_artifacts, load_memory],
    generate_content_config=CREATIVE_CONFIG,
)
