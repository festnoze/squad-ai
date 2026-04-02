"""Corrige exercice 3 - Runtime, Configuration et Artifacts."""

from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext
from google.genai import types

PRECISE_CONFIG = types.GenerateContentConfig(
    temperature=0.2,
    max_output_tokens=500,
)


async def asave_note(title: str, content: str, tool_context: ToolContext) -> dict:
    """Saves a note as a persistent artifact.

    Args:
        title: The note title (used as filename).
        content: The note content.

    Returns:
        Dictionary with save confirmation.
    """
    artifact = types.Part.from_text(text=content)
    version = await tool_context.save_artifact(filename=title, artifact=artifact)
    return {
        "status": "success",
        "message": f"Note '{title}' saved (version {version})",
    }


async def aload_note(title: str, tool_context: ToolContext) -> dict:
    """Loads a previously saved note.

    Args:
        title: The note title to load.

    Returns:
        Dictionary with the note content or error.
    """
    artifact = await tool_context.load_artifact(filename=title)
    if artifact is None:
        return {"status": "error", "message": f"Note '{title}' not found."}
    text = artifact.text if hasattr(artifact, "text") else str(artifact)
    return {"status": "success", "title": title, "content": text}


async def alist_notes(tool_context: ToolContext) -> dict:
    """Lists all saved notes.

    Returns:
        Dictionary with list of note titles.
    """
    files = await tool_context.list_artifacts()
    return {"status": "success", "notes": files if files else [], "count": len(files) if files else 0}


root_agent = Agent(
    name="note_taker",
    model="gemini-2.5-flash",
    description="A note-taking assistant that saves notes as persistent artifacts.",
    instruction=(
        "You are a note-taking assistant.\n"
        "Use asave_note to save notes, aload_note to load them, alist_notes to list all.\n"
        "Always confirm actions to the user."
    ),
    tools=[asave_note, aload_note, alist_notes],
    generate_content_config=PRECISE_CONFIG,
)
