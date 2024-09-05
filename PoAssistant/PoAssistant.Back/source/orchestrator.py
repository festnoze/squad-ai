from misc import misc
from display_helper import display
from datetime import datetime
# internal import
from front_client import front_client
from models.conversation import Conversation, Message
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from openai_helper import ai
from file_helper import file
from langchains.langchain_adapter_generic import LangChainAdapter

class Orchestrator:
    check_end_assistant = None       
    pm_role = "PM"
    business_role = "Métier"
    po_role = "PO"
    qa_role = "QA"
    tag_end_exchange = "[ENDS_EXCHANGE]"
    tag_end_pm_questions = "[FIN_PM_ASSIST]"

    def __init__(self, langchain_adapter: LangChainAdapter, max_exchanges_count: int):
        self.max_exchanges_count: int = max_exchanges_count
        self.langchain: LangChainAdapter = langchain_adapter

    async def perform_workflow_async(self):  
        self.delete_all_outputs()        
        print("Waiting for front-end connection establishment .....")
        front_client.ping_front_until_responding()
        front_client.delete_all_metier_po_thread()
        print("Communication with front-end established!!!")

        # Load roles instructions
        self.business_instructions= file.get_as_str("business_expert_assistant_instructions.txt")
        self.pm_instructions = file.get_as_str("pm_assistant_instructions.txt").format(max_exchanges_count= self.max_exchanges_count)
        self.po_instructions= file.get_as_str("po_us_assistant_instructions.txt")
        self.qa_instructions= file.get_as_str("qa_assistant_instructions.txt")
        
        display.display_llm_infos(self.langchain.llm)

        request_message = front_client.wait_need_expression_creation_and_get()
        print(f"Description initiale de l'objectif : {request_message}")
                
        conversation = await self.do_metier_pm_exchanges_async(request_message)
        self.save_metier_pm_exchanges(conversation)
    
        us_contents = self.create_po_us_and_usecases(conversation)
        self.save_po_us_and_usecases(us_contents)
        return 
    
        # to move to langchain QA tests parallel creation
        threads_ids = await self.write_qa_acceptance_tests_from_us_json_async(us_contents)
        self.save_qa_acceptance_tests(threads_ids)


    async def do_metier_pm_exchanges_async(self, initial_request: str) -> Conversation:
        initial_request_instruction = f"Le besoin fonctionnel central et but à atteindre est : '{initial_request}'."
        business_answer = initial_request_instruction
        conversation = Conversation()
        conversation.add_new_message(Orchestrator.business_role, initial_request_instruction, 0)
        counter = 0        

        while True:
            counter += 1
            
            if business_answer == Orchestrator.tag_end_exchange:
                return conversation
            
            # Security to end exchange if the PM agent didn't follow it's stopping instructions on its own
            if counter > self.max_exchanges_count + 5:
                end_msg = Message(self.pm_role, Orchestrator.tag_end_pm_questions, 0)
                front_client.post_new_metier_or_pm_answer(end_msg)
                conversation.add_message(end_msg)
                return conversation
            
            # Ask PM with latest business expert feedback (or initial need expression):
            # answer_message = self.langchain.invoke_with_conversation(self.langchain.llm, Orchestrator.pm_role, conversation, [self.pm_instructions, initial_request_instruction])
            # front_client.post_new_metier_or_pm_answer(answer_message)

            pm_answer_message = await self.langchain.ask_llm_new_pm_business_message_streamed_to_front_async(
                    user_role= Orchestrator.pm_role,
                    conversation= conversation,
                    instructions= [self.pm_instructions, initial_request_instruction]
            )

            # If PM has no more questions, ask business if they still want to add other points
            if pm_answer_message.content.__contains__(Orchestrator.tag_end_pm_questions):
                business_answer = front_client.wait_metier_answer_validation_and_get() 
                if business_answer != Orchestrator.tag_end_exchange:
                    conversation.add_new_message(Orchestrator.business_role, business_answer, 0)
                continue

            # Ask business with latest PM questions:
            await self.langchain.ask_llm_new_pm_business_message_streamed_to_front_async(
                    user_role= Orchestrator.business_role,
                    conversation= conversation,
                    instructions= [self.business_instructions, initial_request_instruction]
            )

            # Wait for user updation of business answer     
            business_answer = front_client.wait_metier_answer_validation_and_get()

            # Update last conversation message if changed on the front-end
            if conversation.messages[-1].content != business_answer:
                conversation.messages[-1].content = business_answer 

    def create_po_us_and_usecases(self, conversation: Conversation) -> str:
        pm_business_exchange_as_json_str = conversation.get_all_messages_as_json()
        po_instructions_for_us_writing = file.get_as_str("po_message_for_us_and_usecases_creation.txt")
        request_with_instructions = list()
        request_with_instructions.append(SystemMessage(content= self.po_instructions))
        request_with_instructions.append(SystemMessage(content= po_instructions_for_us_writing))
        request_with_instructions.append(HumanMessage(content= f"Voici l'échange sous forme Json :\n{pm_business_exchange_as_json_str}"))        
        
        answer, elapsed = self.langchain.invoke_with_elapse_time(request_with_instructions)
        misc.print_message(Message(Orchestrator.po_role, answer, elapsed))
        return answer
    
    async def write_qa_acceptance_tests_from_us_json_async(self, us_and_usecases_json_str):
        us_and_usecases_json = misc.extract_json_from_text(us_and_usecases_json_str)
        user_story = us_and_usecases_json['us_desc']
        qa_assistant_run_instructions = f"Le contexte globale est une User Story dont la description est : '{user_story}'"
        threads_ids = []
        start_time = datetime.now()
        for usecase_json in us_and_usecases_json['use_cases']:
            # make all QA requests sync (one after another)
            # qa_message = self.get_qa_message_create_acceptance_tests_from__usecase(usecase_json)
            # run_result = ai.add_message_and_run(self.qa_assistant_set, qa_message, qa_assistant_run_instructions)
            # qa_response = ai.get_run_result(self.qa_assistant_set, run_result)
            # elapsed = misc.get_elapsed_time(self.qa_assistant_set.run.created_at, self.qa_assistant_set.run.completed_at)
            # print(f"({elapsed}) Tests from use case:\n{qa_response}\n")

            # make all QA requests in paralell on same assistant
            thread_id = self.new_thread_for_single_qa_acceptance_test(usecase_json)
            threads_ids.append(thread_id)
        results = await ai.run_all_threads_paralell_async(self.qa_assistant_set, threads_ids, qa_assistant_run_instructions)

        if not all(result == ai.RunResult.SUCCESS for result in results):
            print(f"Toutes les requètes QA n'ont pas réussi: \n{misc.array_to_bullet_list_str(results)}")            
            failed_threads_ids = [threads_ids[i] for i in range(len(threads_ids)) if results[i] != ai.RunResult.SUCCESS]
            print(f"Relance des {len(failed_threads_ids)} threads qui ont échoué ...")
            #retry failed
            results = await ai.run_all_threads_paralell_async(self.qa_assistant_set, failed_threads_ids, qa_assistant_run_instructions)
            if all(result == ai.RunResult.SUCCESS for result in results):
                print("Toutes les requètes QA ont maintenant réussi")  
        
        i = 1
        elapsed_seconds = misc.get_elapsed_time_seconds(start_time.timestamp(), datetime.now().timestamp())
        print(f"({elapsed_seconds}s.) QA :\n")
        for thread_id in threads_ids:
            print(f"----- use case {i} ------")
            i += 1
            print(f"\n{ai.get_last_thread_answer(thread_id)}")
        return threads_ids
            

    def new_thread_for_single_qa_acceptance_test(self, usecase_json):
        qa_message = self.get_qa_message_create_acceptance_tests_from__usecase(usecase_json)
        specific_thread = ai.add_new_thread_message(qa_message)
        return specific_thread.id
    
    def get_qa_message_create_acceptance_tests_from__usecase(self, usecase_json):
        qa_init_message = file.get_as_str("qa_message_for_acceptance_tests.txt")
        use_case = usecase_json['uc_desc']
        acceptance_criteria = misc.array_to_bullet_list_str(usecase_json['acceptance_criteria'])
        qa_message = qa_init_message.format(use_case= use_case, acceptance_criteria= acceptance_criteria)
        return qa_message
            
    def save_qa_acceptance_tests(self, threads_ids):
        i = 1
        for thread_id in threads_ids:
            content = misc.str_to_gherkin(ai.get_last_thread_answer(thread_id))
            content = misc.output_parser_gherkin(content)
            file.write_file(content, "AcceptanceTests", f"use_case{i}.feature")
            i += 1

    def save_po_us_and_usecases(self, us_contents: str):
        us_and_usecases_json = misc.extract_json_from_text(us_contents)
        front_client.post_po_us_and_usecases(us_and_usecases_json)
        us_and_usecases_json_str = misc.json_to_str(us_and_usecases_json)
        file.write_file(us_and_usecases_json_str, misc.sharedFolder, "user_story.json")

    def save_metier_pm_exchanges(self, conversation: Conversation):
        messages_json = conversation.get_all_messages_as_json()
        messages_str = misc.json_to_str(messages_json)
        file.write_file(messages_str, misc.sharedFolder, "BusinessExpert_ProductOwner_Exchanges.json")
        
    def delete_all_outputs(self):
        file.delete_folder_contents(misc.sharedFolder)
        file.delete_all_files_with_extension("*.feature", "AcceptanceTests")
        file.delete_all_files_with_extension("*StepDefinitions.cs", "AcceptanceTests")
    
    # def create_check_end_assistant(self):
    #     self.check_end_assistant = self.langchain.create_chat_langchain(
    #         model= "gpt-3.5-turbo-16k",
    #         instructions="Tu es un expert en analyse de phrases, et tu dois toujours répondre uniquement par oui ou non",
    #         run_instructions= "",
    #         timeout_seconds= 20
    #     )

    def has_questions(self, message):
        return message.__contains__("?") or  message.__contains__("merci")

    #don't work proprely
    def has_assistant_detect_question(self, message):
        message = f"Est ce que le texte suivant contient une ou plusieurs questions: \n'{message}'"
        result = ai.add_message_and_run(self.check_end_assistant, message)
        if result != ai.RunResult.SUCCESS:
            return False
        answer = ai.get_last_answer(self.check_end_assistant)
        if answer.__contains__("oui"):
            return True
        return False
        