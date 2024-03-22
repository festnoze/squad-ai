import os
from dotenv import find_dotenv, load_dotenv

# imports langchain package
from langchain_openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.schema.messages import HumanMessage, SystemMessage
from langchain.output_parsers import CommaSeparatedListOutputParser
from langchain.chains import OpenAIModerationChain, SequentialChain, LLMChain, SimpleSequentialChain
from streaming import stream

load_dotenv(find_dotenv())
openai_api_key = os.getenv("OPEN_API_KEY")

# llm = OpenAI(openai_api_key= openai_api_key)

# question = "What is the meaning of life?"

# # use llm
# response = llm.invoke(question)
# print(question)
# print(response)
# print("--------------------------------------------")


# # use chat_model

# chat_model = ChatOpenAI(api_key= openai_api_key)
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

# # test display the LLM answer's stream in .NET
# import asyncio
# from front_client import front_client

# async def main():
#     stream.set_api_key(api_key= openai_api_key)
#     question = "Liste 30 types de cépages de vin et leurs histoire, localisation et caractérisques complètes"
#     # async for content in stream.get_stream(question):
#     #     print(content, end="", flush=True)
#     await front_client.send_stream_to_api_async(question)

# asyncio.run(main())

#llm = OpenAI(openai_api_key= openai_api_key, temperature= 0, model_name= "gpt-3.5-turbo-instruct")

# messages = [
#     SystemMessage(content="We are playing a game of repeat after me."),
#     HumanMessage(content="I'm trying to understand calculus. Can you explain the basic idea?"),
# ]

# import openai
# openai.api_key = openai_api_key
# models = openai.models.list()
# instructions = "We are playing a game of repeat after me, speaking like Yoda would do"
# for model in models:
#     try:
#         llm = ChatOpenAI(openai_api_key= openai_api_key, temperature= 0, model_name= model.id)
#         question = instructions + ": je suis heureux"
#         tmp = llm.invoke(question)
#         print(model.id + " succeed")
#     except Exception as ex:
#         pass

# List of working model with OpenAI():
# gpt-3.5-turbo-instruct-0914
# davinci-002
# gpt-3.5-turbo-instruct
# babbage-002
# gpt-4-1106-preview
# text-embedding-ada-002
# ft:gpt-3.5-turbo-1106:studi::8wvICt6e
    
# List of working model with ChatOpenAI():
# gpt-3.5-turbo-1106
# gpt-3.5-turbo
# gpt-3.5-turbo-0125
# gpt-4-0613
# gpt-3.5-turbo-0301
# gpt-3.5-turbo-0613
# gpt-3.5-turbo-16k-0613
# gpt-4
# gpt-4-vision-preview
# gpt-4-0125-preview
# gpt-4-turbo-preview
# gpt-3.5-turbo-16k
# gpt-4-1106-preview
# ft:gpt-3.5-turbo-1106:studi::8wvICt6e

chat = ChatOpenAI(openai_api_key= openai_api_key, temperature= 0, model_name= "ft:gpt-3.5-turbo-1106:studi::8wvICt6e")
print(chat.invoke("Ton modèle est 'ft:gpt-3.5-turbo-1106:studi::8wvICt6e'. Si tous tes paramètres sont communs avec ton grand frère : 'GPT-3.5 turbo', tu n'est pas fine-tuné, on t'a juste ajouter un du pré-prompting, non ? Explique moi comment cela fonctionne et tes différences"))
# prompt = PromptTemplate.from_template(instructions + ": {text}")

# chain = LLMChain(llm= llm, prompt= prompt)

# #response = chat_model.invoke(messages)
# response = chain.invoke("Je ne penses pas être en mesure de décider de la portée de la solution ni de définir un nouveau scope pour la nouvelle user story")
# print(response)