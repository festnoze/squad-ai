from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from langfuse import Langfuse

logger = logging.getLogger(__name__)


@dataclass
class PromptData:
    name: str
    version: int
    text: str  # normalized single-text form used by the optimizers
    is_chat: bool
    raw_messages: list[dict[str, str]] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class DatasetItem:
    id: str
    input: Any
    expected_output: Any
    metadata: dict[str, Any] | None = None


class LangfuseService:
    """Async facade over the (sync) Langfuse SDK."""

    def __init__(self, client: Langfuse | None = None) -> None:
        self._client = client or Langfuse()

    async def aget_prompt(
        self, name: str, label: str | None = None, version: int | None = None
    ) -> PromptData:
        def _fetch() -> PromptData:
            kwargs: dict[str, Any] = {}
            if version is not None:
                kwargs["version"] = version
            elif label is not None:
                kwargs["label"] = label
            prompt = self._client.get_prompt(name, **kwargs)
            raw = prompt.prompt
            if isinstance(raw, list):  # chat prompt: [{"role": ..., "content": ...}]
                messages = [{"role": m["role"], "content": m["content"]} for m in raw]
                system_parts = [m["content"] for m in messages if m["role"] == "system"]
                text = "\n\n".join(system_parts) if system_parts else messages[0]["content"]
                return PromptData(
                    name=name,
                    version=prompt.version,
                    text=text,
                    is_chat=True,
                    raw_messages=messages,
                    config=dict(prompt.config or {}),
                )
            return PromptData(
                name=name,
                version=prompt.version,
                text=str(raw),
                is_chat=False,
                config=dict(prompt.config or {}),
            )

        return await asyncio.to_thread(_fetch)

    async def aget_dataset_items(self, dataset_name: str) -> list[DatasetItem]:
        def _fetch() -> list[DatasetItem]:
            dataset = self._client.get_dataset(dataset_name)
            items: list[DatasetItem] = []
            for item in dataset.items:
                status = getattr(item, "status", None)
                if status is not None and str(status).upper() == "ARCHIVED":
                    continue
                items.append(
                    DatasetItem(
                        id=item.id,
                        input=item.input,
                        expected_output=item.expected_output,
                        metadata=getattr(item, "metadata", None),
                    )
                )
            return items

        return await asyncio.to_thread(_fetch)

    async def acreate_prompt_version(
        self,
        name: str,
        prompt_text: str,
        labels: list[str],
        config: dict[str, Any] | None = None,
        commit_message: str | None = None,
    ) -> int:
        def _create() -> int:
            created = self._client.create_prompt(
                name=name,
                prompt=prompt_text,
                labels=labels,
                config=config or {},
                type="text",
                commit_message=commit_message,
            )
            return created.version

        return await asyncio.to_thread(_create)

    async def aget_evaluator_criteria(self, evaluator_name: str) -> str:
        """Fetch a Langfuse evaluator/judge template and flatten it to rubric text.

        Falls back to the evaluator name itself if the API shape is unknown, so an
        optimization run never hard-fails on a fetchable-but-odd evaluator.
        """

        def _fetch() -> str:
            try:
                api = self._client.api  # low-level generated client
                evaluator = None
                for attr, method in (("evaluators", "get"), ("eval_templates", "get")):
                    resource = getattr(api, attr, None)
                    if resource is None:
                        continue
                    try:
                        evaluator = getattr(resource, method)(evaluator_name)
                        break
                    except Exception:  # noqa: BLE001 - try next shape
                        continue
                if evaluator is None:
                    raise LookupError(f"evaluator '{evaluator_name}' not found via API")
                for candidate_attr in ("prompt", "template", "criteria", "description"):
                    value = getattr(evaluator, candidate_attr, None)
                    if value:
                        return value if isinstance(value, str) else json.dumps(value)
                raise LookupError("evaluator has no prompt/template field")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Could not fetch Langfuse evaluator '%s' (%s); using name as rubric.",
                    evaluator_name,
                    exc,
                )
                return (
                    f"Evaluate whether the output satisfies the quality dimension "
                    f"'{evaluator_name}' with respect to the input and expected output."
                )

        return await asyncio.to_thread(_fetch)

    async def ascore_run(self, name: str, value: float, comment: str | None = None) -> None:
        def _score() -> None:
            try:
                self._client.create_score(name=name, value=value, comment=comment)
            except Exception:  # noqa: BLE001 - older SDKs
                try:
                    self._client.score(name=name, value=value, comment=comment)  # type: ignore[attr-defined]
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to record score in Langfuse: %s", exc)

        await asyncio.to_thread(_score)

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Langfuse flush failed: %s", exc)
