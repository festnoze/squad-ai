
from groq import Groq
from langchains.langchain_adapter_type import LangChainAdapterType
from models.llm_info import LlmInfo

class GroqHelper:
    @staticmethod
    def test_query(llm_info: LlmInfo):
        if llm_info.type != LangChainAdapterType.Groq:
            print("This method is only for Groq models.")
            return
        
        groq = Groq(api_key=llm_info.api_key)
        chat_completion = groq.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": "what could be the acronym: LLM refers to? Give all known acceptance for this acronym, including those in the field of computer science.",
                }
            ],
            model=llm_info.model,
        )
        print(chat_completion.choices[0].message.content)