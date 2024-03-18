from langchain.llms import OpenAI
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
import langchain.output_parsers

class LangChain:  # Class names typically use CamelCase
    def create_openai_assistant(template, variable):
        llm = OpenAI(temperature=0.9)
        prompt = PromptTemplate(
            input_variables=['topic'],  # Comma added here
            template=template
        )
        chain = LLMChain(
            llm=llm,
            prompt=prompt
        )
        response = chain.run(topic=variable)
        print(response)

        