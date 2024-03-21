import os
from dotenv import find_dotenv, load_dotenv

# imports langchain package
from langchain_openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.schema.messages import HumanMessage, SystemMessage
from langchain.output_parsers import CommaSeparatedListOutputParser
from streaming import stream

load_dotenv(find_dotenv())
openai_api_key = os.getenv("OPEN_API_KEY")

# llm = OpenAI(openai_api_key= openai_api_key)
chat_model = ChatOpenAI(api_key= openai_api_key)

# question = "What is the meaning of life?"

# # use llm
# response = llm.invoke(question)
# print(question)
# print(response)
# print("--------------------------------------------")


# # use chat_model
# response = chat_model.invoke(question)
# print(question)
# answer = response.content
# print(answer)


# # specify several messages and roles
# messages = [
#     SystemMessage(content="You are a personal math tutor that answers questions in the style of Gandalf from The Hobbit."),
#     HumanMessage(content="I'm trying to understand calculus.  Can you explain the basic idea?"),
# ]
# response = chat_model.invoke(messages)
# print(response.content)


# # Create a prompt with placeholders
# template = PromptTemplate.from_template(
#     "What is the capital city of {country}?"
# )
# filled_prompt = template.format(country="Italy")
# print(filled_prompt)



# # Initialize the parser and get instructions on how the LLM output should be formatted
# output_parser = CommaSeparatedListOutputParser()
# format_instructions = output_parser.get_format_instructions()

# # Use a prompt template to get a list of items
# prompt = PromptTemplate(
#     template="The user will pass in a category.  Your job is to return a comma-separated list of 10 values.\n{format_instructions}\n{query}\n",
#     input_variables=["category"],
#     partial_variables={"format_instructions": format_instructions},
# )

# # Define the category to pass to the model
# category = "animals"

# # Chain together the prompt and model, then invoke the model to get structured output
# prompt_and_model = prompt | chat_model
# output = prompt_and_model.invoke({"query": category})

# # Invoke the parser to get the parsed output
# parsed_result = output_parser.invoke(output)

# # Print the parsed result
# print(parsed_result)

import asyncio
from front_client import front_client

async def main():
    stream.set_api_key(api_key= openai_api_key)
    
    question = "Liste 10 types de cépages de vin et leurs histoire, localisation et caractérisques complètes"
    # async for content in stream.get_stream(question):
    #     print(content, end="", flush=True)
    await front_client.send_stream_to_api_async(question)

asyncio.run(main())
