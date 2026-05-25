"""ScopingAgent service — orchestrates the scoping chat with the LLM.

This is the heart of Epic 2: turn a free-form user message into a concrete
project tree (Epic / UserStory / Task) validated by the PM.

The agent:

1. Persists the incoming user message.
2. Loads the project's chat history and current (non-archived) items.
3. Builds the LangChain messages array (SystemMessage + history).
4. Calls the LLM via ``common_tools.llm.llm_helper.Llm.ainvoke``, asking for a
   structured JSON output parsed through ``ExtractedJsonOutputParser``.
5. Creates / updates items in the DB depending on the parsed ``action``.
6. Persists an assistant message including structured ``meta_data``.
7. Returns a `ScopingResult` summarising what happened.

The LLM is provider-agnostic: we pick whatever is declared in ``LLM_INFO``
(OpenAI / Anthropic / Groq / Google / Ollama / OpenRouter). The concrete
instance is produced once by ``app.services.llm_factory.get_llm`` and reused
across turns — `Llm.ainvoke` itself is stateless.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.infrastructure.chat_message_repository import ChatMessageRepository
from app.infrastructure.item_dependency_repository import (
    ItemDependencyRepository,
)
from app.infrastructure.item_repository import ItemRepository
from app.models.chat_message import ChatMessage, ChatMessageRole
from app.models.item import Item, ItemComplexity, ItemStatus, ItemType
from app.models.item_dependency import ItemDependency
from app.services.llm_factory import get_llm
from app.services.prompts.scoping_system_prompt import SCOPING_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Pydantic schema used by ExtractedJsonOutputParser to validate the LLM output
# ---------------------------------------------------------------------------


class ProposedItemModel(BaseModel):
    """Single item entry proposed by the LLM."""

    temp_id: str = Field(description="Temporary id used to link children to their parent.")
    type: str = Field(description="One of: epic, user_story, task.")
    title: str = Field(description="Short actionable title (<80 chars).")
    description: str = Field(default="", description="Detailed description.")
    complexity: str | None = Field(
        default=None,
        description="One of: simple, medium, complex.",
    )
    parent_temp_id: str | None = Field(
        default=None,
        description="temp_id of the parent item, or null if this is a root item.",
    )
    acceptance_criteria: list[str] | None = Field(
        default=None,
        description="3 to 7 testable acceptance criteria (mainly for user_story).",
    )
    depends_on_temp_ids: list[str] | None = Field(
        default=None,
        description=(
            "temp_ids of other tasks that must finish before this task starts. "
            "Only used when type=='task'. None or empty otherwise."
        ),
    )


class ScopingResponse(BaseModel):
    """Top-level JSON schema returned by the LLM on every turn."""

    action: str = Field(
        description=(
            "One of: propose_items (new tree proposal), ask_question (clarify), "
            "confirm (PM validated, move PROPOSED items to TODO)."
        ),
    )
    message: str = Field(
        description="Free text message shown in the chat UI, written in French.",
    )
    items: list[ProposedItemModel] = Field(
        default_factory=list,
        description="List of items to create; only populated when action=propose_items.",
    )


# JSON format instructions injected into the prompt so the LLM knows exactly
# what shape to return. We keep it separate from SCOPING_SYSTEM_PROMPT so the
# Agent B's prompt (12 sections) stays intact.
_JSON_FORMAT_INSTRUCTIONS = """\

# Format de sortie OBLIGATOIRE

Tu dois répondre UNIQUEMENT avec un objet JSON valide (pas de markdown, pas de
texte libre autour) respectant EXACTEMENT ce schéma :

{
  "action": "propose_items" | "ask_question" | "confirm",
  "message": "Message texte en français pour le PM dans le chat",
  "items": [
    {
      "temp_id": "epic-1",
      "type": "epic" | "user_story" | "task",
      "title": "Titre court actionnable",
      "description": "Description détaillée",
      "complexity": "simple" | "medium" | "complex",
      "parent_temp_id": null | "temp_id d'un autre item",
      "acceptance_criteria": ["critère 1", "critère 2", ...],
      "depends_on_temp_ids": ["temp_id d'une autre task", ...]
    }
  ]
}

Règles de remplissage :
- "items" est obligatoirement rempli UNIQUEMENT si action == "propose_items" ;
  sinon c'est une liste vide [].
- "parent_temp_id" est null pour les items racine, sinon il référence un
  temp_id d'un autre item de la MÊME réponse.
- "acceptance_criteria" est obligatoire pour type == "user_story" (3 à 7
  entrées), optionnel pour task, non utilisé pour epic.
- "depends_on_temp_ids" est une liste de temp_id de tasks de la MÊME réponse
  qui doivent être terminées avant celle-ci. Utilisé uniquement sur les
  tasks. Laisse-la vide si aucune dépendance n'existe (c'est le cas le plus
  fréquent — ne surdétermine pas). Jamais de cycles.
- Ordre recommandé dans "items" : epics d'abord, puis user_stories, puis tasks.

Réponds UNIQUEMENT avec le JSON. Aucun texte avant ni après.
"""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ScopingResult:
    """Outcome of a single `aprocess_user_message` call.

    Attributes:
        assistant_message: The persisted assistant-side `ChatMessage`.
        items_created: Items newly created during this turn (status=PROPOSED
            for ``propose_items`` actions, empty otherwise).
        items_updated: Items whose status changed during this turn (typically
            PROPOSED -> TODO for ``confirm`` actions).
        action: The action taken by the LLM —
            ``propose_items`` / ``ask_question`` / ``confirm`` / ``error``.
    """

    assistant_message: ChatMessage
    items_created: list[Item] = field(default_factory=list)
    items_updated: list[Item] = field(default_factory=list)
    action: str = "ask_question"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class ScopingAgent:
    """Orchestrates a conversation with the LLM to scope a project.

    Uses `Llm.ainvoke` from common-tools so the provider is pluggable via the
    ``LLM_INFO`` environment variable.
    """

    def __init__(
        self,
        chat_repository: ChatMessageRepository,
        item_repository: ItemRepository,
        dependency_repository: ItemDependencyRepository | None = None,
    ) -> None:
        self.chat_repository = chat_repository
        self.item_repository = item_repository
        self.dependency_repository = dependency_repository
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def aprocess_user_message(
        self,
        project_id: UUID,
        user_content: str,
    ) -> ScopingResult:
        """Handle a new user message for the given project."""
        # 1. Persist the user message so it becomes part of the history.
        await self.chat_repository.acreate_message(
            ChatMessage(
                project_id=project_id,
                role=ChatMessageRole.USER,
                content=user_content,
            ),
        )

        # 2. Load the full chat history (includes the message we just wrote).
        history = await self.chat_repository.aget_messages_by_project(project_id)

        # 3. Load the current items (everything that isn't soft-deleted).
        current_items = await self.item_repository.aget_items_by_project(project_id)

        # 4. Build the LangChain message list + context-aware system prompt.
        lc_messages = self._build_langchain_messages(
            history=history,
            current_items=current_items,
        )

        # 5. Call the LLM — defensive wrapping: network / quota / JSON errors
        #    must not blow up the request, we persist a friendly error instead.
        try:
            parsed = await self._ainvoke_llm(lc_messages)
        except Exception as exc:  # noqa: BLE001 — we want a catch-all here
            self.logger.exception("LLM call or JSON parsing failed")
            return await self._apersist_error_response(project_id, exc)

        # 6. Extract action + assistant message text.
        action = self._extract_action(parsed)
        assistant_text = self._extract_message(parsed)

        # 7. Materialise side-effects based on the action.
        items_created: list[Item] = []
        items_updated: list[Item] = []

        if action == "propose_items":
            items_created = await self._acreate_proposed_items(
                project_id=project_id,
                parsed=parsed,
            )
        elif action == "confirm":
            items_updated = await self._aconfirm_proposed_items(project_id)

        # 8. Persist the assistant message with structured meta_data.
        assistant_message = await self._apersist_assistant_message(
            project_id=project_id,
            content=assistant_text,
            action=action,
            items_created=items_created,
            items_updated=items_updated,
            raw_parsed=parsed,
        )

        # 9. Return the result bundle.
        return ScopingResult(
            assistant_message=assistant_message,
            items_created=items_created,
            items_updated=items_updated,
            action=action,
        )

    # ------------------------------------------------------------------
    # LangChain message building
    # ------------------------------------------------------------------

    def _build_system_prompt(self, current_items: list[Item]) -> str:
        """Prefix the base system prompt with a JSON dump of current items.

        Also appends the JSON format instructions so the LLM understands the
        exact shape we want (replacement for native tool-use).
        """
        summary = [
            {
                "id": str(item.id),
                "type": item.type.value,
                "title": item.title,
                "status": item.status.value,
                "parent_id": str(item.parent_id) if item.parent_id else None,
                "complexity": (
                    item.complexity.value if item.complexity is not None else None
                ),
            }
            for item in current_items
        ]
        context_block = (
            "<current_project_items>\n"
            f"{json.dumps(summary, ensure_ascii=False)}\n"
            "</current_project_items>\n\n"
        )
        return context_block + SCOPING_SYSTEM_PROMPT + _JSON_FORMAT_INSTRUCTIONS

    def _build_langchain_messages(
        self,
        history: list[ChatMessage],
        current_items: list[Item],
    ) -> list[Any]:
        """Build a list of LangChain ``BaseMessage`` objects.

        Shape:
            [
                SystemMessage(...),
                HumanMessage(...),    # oldest user turn
                AIMessage(...),       # assistant reply
                ...
                HumanMessage(...),    # most recent user turn
            ]

        System messages stored in the DB are skipped (their content is already
        merged into the dedicated ``SystemMessage`` that leads the list).
        """
        from langchain_core.messages import (
            AIMessage,
            BaseMessage,
            HumanMessage,
            SystemMessage,
        )

        messages: list[BaseMessage] = [
            SystemMessage(content=self._build_system_prompt(current_items)),
        ]
        for msg in history:
            if msg.role == ChatMessageRole.USER:
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == ChatMessageRole.ASSISTANT:
                messages.append(AIMessage(content=msg.content))
            # SYSTEM entries from the DB are intentionally dropped.
        return messages

    # ------------------------------------------------------------------
    # LLM invocation (common-tools)
    # ------------------------------------------------------------------

    async def _ainvoke_llm(self, lc_messages: list[Any]) -> dict[str, Any]:
        """Call ``Llm.ainvoke`` with a JSON output parser.

        Returns a dict conforming to `ScopingResponse` (validated by Pydantic
        via ``ExtractedJsonOutputParser``).
        """
        # Imported lazily so the app can still boot and run the CRUD tests
        # even if common-tools is not yet installed in the environment.
        from common_tools.llm.extracted_json_output_parser import (
            ExtractedJsonOutputParser,
        )
        from common_tools.llm.llm_helper import Llm

        llm = get_llm()
        parser = ExtractedJsonOutputParser(pydantic_object=ScopingResponse)

        response = await Llm.ainvoke(
            llm_or_llms=llm,
            prompt_or_prompts=lc_messages,
            parser=parser,
            action_name="scoping_agent.aprocess_user_message",
        )

        # With a parser, Llm.ainvoke returns a dict (or a list of dicts if we
        # had passed multiple prompts). We only pass one conversation, so the
        # return type should be a single dict.
        if isinstance(response, list):
            if not response:
                return {}
            response = response[0]
        if not isinstance(response, dict):
            raise TypeError(
                f"LLM returned unexpected non-dict payload: {type(response).__name__}",
            )
        return response

    # ------------------------------------------------------------------
    # Parsed response extraction
    # ------------------------------------------------------------------

    def _extract_action(self, parsed: dict[str, Any]) -> str:
        """Return the action or fall back to ``ask_question``."""
        action = parsed.get("action") if parsed else None
        if isinstance(action, str) and action in {
            "propose_items",
            "ask_question",
            "confirm",
        }:
            return action
        return "ask_question"

    @staticmethod
    def _extract_message(parsed: dict[str, Any]) -> str:
        """Return the ``message`` field or an empty string."""
        value = parsed.get("message") if parsed else None
        if isinstance(value, str):
            return value.strip()
        return ""

    # ------------------------------------------------------------------
    # Item side-effects
    # ------------------------------------------------------------------

    async def _acreate_proposed_items(
        self,
        project_id: UUID,
        parsed: dict[str, Any],
    ) -> list[Item]:
        """Create every proposed item in the DB with status=PROPOSED.

        Items are created in dependency order (epic -> user_story -> task) so
        ``parent_temp_id`` references always resolve to an already-persisted
        row. A ``temp_id -> real UUID`` map is built along the way.

        After the items are created, the V1 ``depends_on_temp_ids`` edges
        (if any) are resolved against the same map and persisted as
        `ItemDependency` rows. Unknown temp_ids are silently dropped —
        the orchestrator will treat the task as having no incoming deps
        rather than crashing.
        """
        raw_items = parsed.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            return []

        ordered_type_buckets: dict[str, list[dict[str, Any]]] = {
            "epic": [],
            "user_story": [],
            "task": [],
        }
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            item_type = raw.get("type")
            if isinstance(item_type, str) and item_type in ordered_type_buckets:
                ordered_type_buckets[item_type].append(raw)

        temp_id_to_uuid: dict[str, UUID] = {}
        created: list[Item] = []
        # We collect raw task payloads so we can persist their
        # ``depends_on_temp_ids`` edges in a second pass once every
        # item UUID is known.
        raw_task_payloads: list[dict[str, Any]] = []

        for bucket_type in ("epic", "user_story", "task"):
            for raw in ordered_type_buckets[bucket_type]:
                try:
                    item = self._build_item_from_parsed_payload(
                        raw=raw,
                        project_id=project_id,
                        temp_id_to_uuid=temp_id_to_uuid,
                    )
                except ValueError as exc:
                    self.logger.warning(
                        "Skipping invalid item payload: %s (error: %s)",
                        raw,
                        exc,
                    )
                    continue

                stored = await self.item_repository.acreate_item(item)
                created.append(stored)

                temp_id = raw.get("temp_id")
                if isinstance(temp_id, str) and stored.id is not None:
                    temp_id_to_uuid[temp_id] = stored.id

                if bucket_type == "task" and isinstance(temp_id, str):
                    raw_task_payloads.append(raw)

        # Persist dependencies (best-effort: skip unknown temp_ids and
        # skip entirely if the repository was not injected — which is
        # the case in legacy tests that never asked for V1 behaviour).
        if self.dependency_repository is not None and raw_task_payloads:
            await self._apersist_task_dependencies(
                raw_task_payloads=raw_task_payloads,
                temp_id_to_uuid=temp_id_to_uuid,
            )

        return created

    async def _apersist_task_dependencies(
        self,
        raw_task_payloads: list[dict[str, Any]],
        temp_id_to_uuid: dict[str, UUID],
    ) -> None:
        """Resolve ``depends_on_temp_ids`` and insert one edge per dep."""
        if self.dependency_repository is None:
            return
        edges: list[ItemDependency] = []
        for raw in raw_task_payloads:
            task_temp_id = raw.get("temp_id")
            if not isinstance(task_temp_id, str):
                continue
            task_uuid = temp_id_to_uuid.get(task_temp_id)
            if task_uuid is None:
                continue
            raw_deps = raw.get("depends_on_temp_ids")
            if not isinstance(raw_deps, list) or not raw_deps:
                continue
            for dep_temp_id in raw_deps:
                if not isinstance(dep_temp_id, str):
                    continue
                dep_uuid = temp_id_to_uuid.get(dep_temp_id)
                if dep_uuid is None or dep_uuid == task_uuid:
                    # Unknown temp_id or self-dependency: silently drop
                    # to stay permissive vs a fallible LLM output.
                    continue
                edges.append(
                    ItemDependency(
                        item_id=task_uuid,
                        depends_on_item_id=dep_uuid,
                    ),
                )
        if edges:
            await self.dependency_repository.acreate_many(edges)

    def _build_item_from_parsed_payload(
        self,
        raw: dict[str, Any],
        project_id: UUID,
        temp_id_to_uuid: dict[str, UUID],
    ) -> Item:
        """Convert a single parsed item dict into a domain `Item`."""
        raw_type = raw.get("type")
        if raw_type not in {t.value for t in ItemType}:
            raise ValueError(f"Invalid item type: {raw_type!r}")

        complexity: ItemComplexity | None = None
        raw_complexity = raw.get("complexity")
        if isinstance(raw_complexity, str) and raw_complexity in {
            c.value for c in ItemComplexity
        }:
            complexity = ItemComplexity(raw_complexity)

        parent_id: UUID | None = None
        parent_temp_id = raw.get("parent_temp_id")
        if isinstance(parent_temp_id, str) and parent_temp_id:
            parent_id = temp_id_to_uuid.get(parent_temp_id)

        acceptance_criteria = raw.get("acceptance_criteria")
        if acceptance_criteria is not None and not isinstance(
            acceptance_criteria, list,
        ):
            acceptance_criteria = None

        return Item(
            project_id=project_id,
            parent_id=parent_id,
            type=ItemType(raw_type),
            title=str(raw.get("title", "")).strip() or "(untitled)",
            description=raw.get("description"),
            complexity=complexity,
            status=ItemStatus.PROPOSED,
            acceptance_criteria=acceptance_criteria,
        )

    async def _aconfirm_proposed_items(self, project_id: UUID) -> list[Item]:
        """Move every PROPOSED item of the project to TODO."""
        all_items = await self.item_repository.aget_items_by_project(project_id)
        updated: list[Item] = []
        for item in all_items:
            if item.status != ItemStatus.PROPOSED or item.id is None:
                continue
            refreshed = await self.item_repository.aupdate_item(
                item.id,
                status=ItemStatus.TODO,
            )
            if refreshed is not None:
                updated.append(refreshed)
        return updated

    # ------------------------------------------------------------------
    # Assistant message persistence
    # ------------------------------------------------------------------

    async def _apersist_assistant_message(
        self,
        project_id: UUID,
        content: str,
        action: str,
        items_created: list[Item],
        items_updated: list[Item],
        raw_parsed: dict[str, Any],
    ) -> ChatMessage:
        """Persist the assistant turn with meta_data useful for the UI + debug."""
        meta_data: dict[str, Any] = {
            "action": action,
            "items_proposed": [str(it.id) for it in items_created if it.id],
            "items_updated": [str(it.id) for it in items_updated if it.id],
            "raw_parsed": raw_parsed,
        }
        return await self.chat_repository.acreate_message(
            ChatMessage(
                project_id=project_id,
                role=ChatMessageRole.ASSISTANT,
                content=content or "",
                meta_data=meta_data,
            ),
        )

    async def _apersist_error_response(
        self,
        project_id: UUID,
        exc: Exception,
    ) -> ScopingResult:
        """Persist a friendly error message and return an empty result."""
        error_content = (
            "Désolé, je n'ai pas pu traiter votre demande. "
            f"Erreur: {exc}"
        )
        assistant_message = await self.chat_repository.acreate_message(
            ChatMessage(
                project_id=project_id,
                role=ChatMessageRole.ASSISTANT,
                content=error_content,
                meta_data={"action": "error", "error": str(exc)},
            ),
        )
        return ScopingResult(
            assistant_message=assistant_message,
            items_created=[],
            items_updated=[],
            action="error",
        )
