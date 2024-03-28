import os
from dotenv import find_dotenv, load_dotenv

# imports langchain package
from langchain_openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain.agents.openai_assistant import OpenAIAssistantRunnable

from langchain.prompts import PromptTemplate, ChatPromptTemplate, HumanMessagePromptTemplate, MessagesPlaceholder
from langchain.schema.messages import HumanMessage, SystemMessage, FunctionMessage
#from langchain_core.messages import SystemMessage
from langchain.output_parsers import CommaSeparatedListOutputParser
from langchain.memory import ConversationBufferMemory
from langchain.chains import OpenAIModerationChain, SequentialChain, LLMChain, SimpleSequentialChain, ConversationChain
from streaming import stream
from conversation import Conversation, Message

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
#     HumanMessage(content="I'm trying to understand calculus. Can you explain the basic idea?"),
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

# test display the LLM answer's stream in .NET
import asyncio
from front_client import front_client

async def main():
    stream.set_api_key(api_key= openai_api_key)
    question = "Liste 3 types de cépages de vin et leurs histoire, localisation et caractérisques complètes"
    # async for content in stream.get_stream(question):
    #     print(content, end="", flush=True)
    content_stream = stream.get_chatgpt_answer_as_stream_async(question)
    await front_client.send_stream_to_api_async(content_stream)

asyncio.run(main())

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

# assist = OpenAIAssistantRunnable.create_assistant(    
#     api_key= openai_api_key,
#     name="langchain assistant",
#     instructions="You are a personal math tutor. Write and run code to answer math questions.",
#     tools=[{"type": "code_interpreter"}],
#     model="gpt-4-1106-preview",
# )
# res = assist.invoke({"content": "What's 10 - 4 raised to the 2.7"})
#print(res)

# chat = ChatOpenAI(openai_api_key= openai_api_key, temperature= 0, model_name= "gpt-4-turbo-preview")
# messages = [
#     HumanMessage(content="Mon nom est MILLER"),
#     HumanMessage(content="Mon prénom est Etienne"),    
#     SystemMessage(content="Hello Etienne"),
#     HumanMessage(content="Quel est mon nom entier ?"),
# ]

# memory=ConversationBufferMemory(chat_memory=messages)
# print(chat.invoke(messages).content)
# prompt = PromptTemplate.from_template(instructions + ": {text}")

# chain = LLMChain(llm= llm, prompt= prompt)

# #response = chat_model.invoke(messages)
# response = chain.invoke("Je ne penses pas être en mesure de décider de la portée de la solution ni de définir un nouveau scope pour la nouvelle user story")
# print(response)


# # test of memory usage
# chat_model = ChatOpenAI(api_key= openai_api_key, timeout= 20)

# # Création d'une conversation
# conversation = Conversation()

# # Ajout de messages à la conversation
# conversation.add_message(Message(role="system", content="You are a personal math tutor that try avoid answering questions because you don't know nothing about maths, if you can't avoid, answer some vague things."))
# conversation.add_message(Message(role="human", content="I'm Etienne. I'm trying to understand calculus. Can you explain the basic idea?"))
# conversation.add_message(Message(role="AI", content="It's so easy Etienne, you should know that. Have a look to your courses if needed."))

# # Génération de la mémoire pour un rôle spécifique
# memory = conversation.to_memory(user_role="human")
# conversation = ConversationChain(
#     llm= chat_model,
#     memory= memory,
# )
# conversation.invoke(input= "i prefer you explain it to me again!")

# for msg in memory.chat_memory.messages:
#     print(msg.content)
