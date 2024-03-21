from langchain_openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.schema.messages import HumanMessage, SystemMessage
from langchain.output_parsers import CommaSeparatedListOutputParser

class stream:
    openai_api_key = ""
    new_line_for_stream = "\\/%*/\\"
    def set_api_key(api_key):
        stream.openai_api_key = api_key

    async def get_chatgpt_answer_as_stream_async(message):
        chat = ChatOpenAI(api_key= stream.openai_api_key)
        async for chunk in chat.astream(message):
            content = chunk.content.replace('\r\n', '\n').replace('\n', stream.new_line_for_stream)
            print(content, end= "", flush= True)
            yield content.encode('utf-8')


