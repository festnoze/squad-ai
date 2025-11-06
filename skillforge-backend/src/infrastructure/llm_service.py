import logging
import re
from typing import AsyncGenerator
from models.thread import Thread

#
from langchain.schema.messages import HumanMessage, SystemMessage
from langchain_core.messages.base import BaseMessage

#
from common_tools.helpers.env_helper import EnvHelper  # type: ignore[import-untyped]
from common_tools.langchains.langchain_factory import LangChainFactory  # type: ignore[import-untyped]
from common_tools.helpers.llm_helper import Llm  # type: ignore[import-untyped]
from utils.prompt_helper import PromptHelper


class LlmService:
    """Handles all LLM calls."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        llms_infos = EnvHelper.get_llms_infos_from_env_config()
        self.llms = LangChainFactory.create_llms_from_infos(llms_infos)

    async def aquery(
        self, thread: Thread, academic_level: str, lesson_breadcrumb: str, lesson_content: str, is_stream_decoded: bool = False, all_response_chunks: list[str] | None = None, llm_index: int = -1
    ) -> AsyncGenerator[str, None]:
        """Pass user query with thread history for the LLM to answer"""
        if not thread.messages:
            raise ValueError("Thread has no messages, so no user query the LLM can answer.")

        last_message = thread.messages[-1]
        if last_message.role.name != "user":
            raise ValueError("Last message is not a user query, so no user query the LLM can answer.")
        user_query = last_message.content

        thread_history = "\n- ".join([f"{msg.role}: {msg.content}" for msg in thread.messages[:-1]])
        if not thread_history:
            thread_history = "- pas de messages précédents -"
        full_prompt = PromptHelper.aget_prompt("query_course_content_prompt.txt", remove_comments=True)
        full_prompt = full_prompt.replace("{lesson_breadcrumb}", lesson_breadcrumb or "")
        full_prompt = full_prompt.replace("{academic_level}", academic_level or "")
        full_prompt = full_prompt.replace("{lesson_content}", lesson_content or "")
        full_prompt = full_prompt.replace("{thread_history}", thread_history or "")

        messages: list[BaseMessage] = []
        # Extract all system messages from XML tags
        system_messages = re.findall(r"<system_message>(.*?)</system_message>", full_prompt, re.DOTALL)
        for message in system_messages:
            messages.append(SystemMessage(message.strip()))
        messages.append(HumanMessage(user_query))

        async_streaming_response = Llm.invoke_as_async_stream("Stream user query answer", self.llms[llm_index], messages, all_response_chunks, False)
        # response = f"Voici une réponse générée automatiquement pour répondre à votre question.\nLa réponse est générée par l'IA SkillForge.\nIl s'agit d'un test pour tester l'envoi de données binaires sous forme de streaming en réponse à la requête de l'utilisateur suivante : \"{user_query}\".\n\nVoici l'historique de la conversation :\n{thread_history}\n\n"
        # words = response.split(" ")

        # Streaming of LLM response
        async for response_chunk in async_streaming_response:
            response_chunk_final = response_chunk if not is_stream_decoded else response_chunk.decode("utf-8").replace(Llm.new_line_for_stream_over_http, "\n")
            yield response_chunk_final

    async def asummarize_content(self, content_to_summarize: str, summary_type: str = "full", llm_index: int = -1) -> str:
        """Generate a summary of the provided content.

        Args:
            content_to_summarize: The content to summarize
                - For "full": original full content (markdown format)
                - For "light": the full summary from previous step
                - For "compact": the light summary from previous step
            summary_type: Type of summary to generate - "full", "light", or "compact"

        Returns:
            Generated summary as a string
        """
        # Define prompt filenames based on type (prompts/ prefix added automatically by PromptHelper)
        prompt_files = {
            "full": "summarize_content_full_prompt.txt",
            "light": "summarize_content_light_prompt.txt",
            "compact": "summarize_content_compact_prompt.txt",
        }

        prompt_filename = prompt_files.get(summary_type, prompt_files["full"])

        # Load the system message from the prompt file (with caching)
        system_message = PromptHelper.aget_prompt(prompt_filename, remove_comments=True)

        # Create messages for LLM
        messages: list[BaseMessage] = [SystemMessage(system_message), HumanMessage(content_to_summarize)]

        # Use non-streaming invoke for simplicity
        response: str = await Llm.invoke_prompt_async(f"summarize_{summary_type}", self.llms[llm_index], messages)
        return response
