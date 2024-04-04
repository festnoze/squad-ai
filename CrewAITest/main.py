import os
from dotenv import find_dotenv, load_dotenv
from crewai import Agent, Task, Crew, Process
from langchain.llms.ollama import Ollama

# internal imports
from env import env
from file import file
from streaming import stream
from conversation import Conversation, Message
from orch import Orchestrator

load_dotenv(find_dotenv())
openai_api_key = os.getenv("OPEN_API_KEY")
env.api_key = openai_api_key

max_exchanges_count = 5
pm_agent = Agent(
    role= "project manager",
    goal= file.get_as_str("pm_assistant_instructions.txt").format(max_exchanges_count= max_exchanges_count),
    backstory= "",
    verbose= True,
    allow_delegation= False,
    openai_api_key= openai_api_key
)

business_agent = Agent(
    role= "business expert",
    goal= file.get_as_str("business_expert_assistant_instructions.txt"),
    backstory= "",
    verbose= True,
    allow_delegation= False,
    openai_api_key= openai_api_key
)

po = Agent(
    role= "product owner",
    goal= file.get_as_str("po_us_assistant_instructions.txt"),
    backstory= "",
    verbose= True,
    allow_delegation= False,
   openai_api_key= openai_api_key
)

#orchestrator workload

def do_metier_pm_exchanges(initial_request: str) -> Conversation:
        initial_request_instruction = f"Le besoin fonctionnel central et but à atteindre est : '{initial_request}'."
        business_answer = initial_request_instruction
        conversation = Conversation()
        conversation.add_new_message(Orchestrator.business_role, initial_request_instruction, 0)
        counter = 0        
        ask_pm = Task(
                description= "The product manager, which is able to analyse and ask question about the need to the business expert",
                agent= pm_agent, 
                expected_output= business_answer
                )
        ask_business = Task(
                description= "The business expert, which is able to answer all questions about the product and the awaited need",
                agent= business_agent,
                expected_output= initial_request_instruction + "\nCombien de destinataires maximum à la fois lors de la création d'un message ?"
                )
        crew = Crew(
             agents= [pm_agent, business_agent],
             tasks= [ask_pm, ask_business],
             process= Process.sequential,
             verbose= 2,
             language= 'en', #TODO: set 'fr' but need somefr.json file to look for
        )
        result = crew.kickoff()
        print(result)
        return None
        # while True:
        #     counter += 1
        #     if counter > self.max_exchanges_count or business_answer == Orchestrator.tag_end_exchange:
        #         return conversation
        #     pm_answer_message = await lc.ask_llm_new_pm_business_message_streamed_to_front_async(
        #                 chat_model= self.pm_llm,
        #                 user_role= Orchestrator.pm_role,
        #                 conversation= conversation,
        #                 instructions= [self.pm_instructions, initial_request_instruction]
        #     )


        #     # If PM has no more questions, ask business if they still want to add other points
        #     if pm_answer_message.content.__contains__(Orchestrator.tag_end_pm_questions):
        #         business_answer = front_client.wait_metier_answer_validation_and_get() 
        #         if business_answer != Orchestrator.tag_end_exchange:
        #             conversation.add_new_message(Orchestrator.business_role, business_answer, 0)
        #         continue

        #     business_message = await lc.ask_llm_new_pm_business_message_streamed_to_front_async(
        #                 chat_model= self.business_llm,
        #                 user_role= Orchestrator.business_role,
        #                 conversation= conversation,
        #                 instructions= [self.business_instructions, initial_request_instruction]
        #     ) 

        #     # Ask business with latest PM questions & run:
        #     # business_message = lc.invoke_with_conversation(
        #     #                     chat_model= self.business_llm,
        #     #                     user_role= Orchestrator.business_role,
        #     #                     conversation= conversation,
        #     #                     instructions= [self.business_instructions, initial_request_instruction]
        #     #                 )
        #     # misc.print_message(business_message)            
        #     # front_client.post_new_metier_or_pm_answer(business_message)   
                 
        #     business_answer = front_client.wait_metier_answer_validation_and_get()

        #     # update last conversation message if changed on the front-end
        #     if conversation.messages[-1].content != business_answer:
        #         conversation.messages[-1].content = business_answer 

do_metier_pm_exchanges('crée un module de messagerie')