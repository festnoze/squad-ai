from langchain_openai import OpenAI
from langchain_openai import ChatOpenAI
from typing import AsyncGenerator

class stream:
    openai_api_key = ""
    new_line_for_stream = "\\/%*/\\"
    def set_api_key(api_key):
        stream.openai_api_key = api_key

    async def get_chatgpt_answer_as_stream_async(message, display_console: bool = True) -> AsyncGenerator[bytes, None]:
        chat = ChatOpenAI(api_key= stream.openai_api_key)
        async for chunk in chat.astream(message):
            content = chunk.content
            if display_console:
                print(content, end= "", flush= True)
            content = content.replace('\r\n', '\n').replace('\n', stream.new_line_for_stream)
            yield content.encode('utf-8')