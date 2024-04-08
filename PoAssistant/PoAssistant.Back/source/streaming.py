from langchain_openai import OpenAI
from langchain_openai import ChatOpenAI

from models.stream_container import StreamContainer

class stream:
    openai_api_key = ""
    new_line_for_stream = "\\/%*/\\"
    def set_api_key(api_key):
        stream.openai_api_key = api_key

    async def get_llm_answer_stream_not_await_async(llm, input, full_stream: StreamContainer, display_console: bool = True):
        async for chunk in llm.astream(input):
            content = chunk.content
            if display_console:
                print(content, end= "", flush= True)
            full_stream.add_content(content)
            content = content.replace('\r\n', '\n').replace('\n', stream.new_line_for_stream)
            yield content.encode('utf-8')