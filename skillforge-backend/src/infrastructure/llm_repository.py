from typing import AsyncGenerator
from models.thread import Thread

#
from langchain.schema.messages import HumanMessage, SystemMessage
from langchain_core.messages.base import BaseMessage

#
from common_tools.helpers.env_helper import EnvHelper  # type: ignore[import-untyped]
from common_tools.langchains.langchain_factory import LangChainFactory  # type: ignore[import-untyped]
from common_tools.helpers.llm_helper import Llm  # type: ignore[import-untyped]
from common_tools.helpers.file_helper import file  # type: ignore[import-untyped]


class LlmRepository:
    """Handles filling of static/reference data into the database."""

    def __init__(self) -> None:
        llms_infos = EnvHelper.get_llms_infos_from_env_config()
        self.llm = LangChainFactory.create_llms_from_infos(llms_infos)[-1]

    async def aquery(self, thread: Thread, context_content: str, ressource_name: str, parcours_name: str, is_stream_decoded: bool = False, all_response_chunks: list[str] | None = None) -> AsyncGenerator[str, None]:
        """Pass user query with thread history for the LLM to answer"""
        if not thread.messages:
            raise ValueError("Thread has no messages, so no user query the LLM can answer.")

        last_message = thread.messages[-1]
        if last_message.role.name != "user":
            raise ValueError("Last message is not a user query, so no user query the LLM can answer.")
        user_query = last_message.content

        system_messages = file.get_as_str("prompts/query_course_content_prompt.txt", remove_comments=True)
        system_messages = system_messages.replace("{parcours_name}", parcours_name)
        system_messages = system_messages.replace("{ressource_name}", ressource_name)
        system_messages = system_messages.replace("{course_content}", context_content)

        messages: list[BaseMessage] = []
        for message in system_messages.split("<separator>"):
            messages.append(SystemMessage(message))
        messages.append(HumanMessage(user_query))

        async_streaming_response = Llm.invoke_as_async_stream("Stream user query answer", self.llm, messages, all_response_chunks, False)
        # response = f"Voici une réponse générée automatiquement pour répondre à votre question.\nLa réponse est générée par l'IA SkillForge.\nIl s'agit d'un test pour tester l'envoi de données binaires sous forme de streaming en réponse à la requête de l'utilisateur suivante : \"{user_query}\".\n\nVoici l'historique de la conversation :\n{thread_history}\n\n"
        # words = response.split(" ")

        # Streaming of LLM response
        async for response_chunk in async_streaming_response:
            response_chunk_final = response_chunk if not is_stream_decoded else response_chunk.decode("utf-8").replace(Llm.new_line_for_stream_over_http, "\n")
            yield response_chunk_final
