from misc import misc
from display_helper import display
from datetime import datetime
from file import file
from front_client import front_client
from langchain_openai_adapter import lc
from models.conversation import Conversation, Message
from openai_helper import ai

class assistants_ochestrator:
    check_end_assistant = None
    def __init__(self, max_exchanges_count):
        self.max_exchanges_count = max_exchanges_count

    async def perform_workflow_async(self):  
        self.delete_all_outputs()        
        print("Waiting for front-end connection establishment .....")
        front_client.ping_front_until_responding()
        front_client.delete_all_metier_po_thread()
        print("Communication with front-end established!!!")

        self.create_assistants()
        self.print_assistants_ids()

        request_message = front_client.wait_need_expression_creation_and_get()
        print(f"Description initiale de l'objectif : {request_message}")
                
        conversation = self.do_metier_pm_exchanges(request_message)
        self.save_metier_po_exchange(conversation)
    
        self.create_po_us_and_usecases(conversation)
        self.save_po_us_and_usecases()
        
        threads_ids = await self.create_qa_acceptance_tests_async()
        self.save_qa_acceptance_tests(threads_ids)

    def do_metier_pm_exchanges(self, initial_request: str) -> Conversation:
        pm_role = "PM"
        business_role = "Métier"
        initial_request_instruction = f"Le besoin fonctionnel central et but à atteindre est : '{initial_request}'."
        business_answer = initial_request_instruction
        conversation = Conversation()
        conversation.add_message(business_role, initial_request_instruction, 0)
        counter = 0        

        while True:
            counter += 1
            if counter > self.max_exchanges_count:
                return conversation
            if business_answer.__contains__("[ENDS_EXCHANGE]"):
                return conversation
            
            # Ask PM with latest business' answer (or the initial request on first shot):
            instructions = [self.pm_instructions]
            if len(conversation.messages) > 1:
                instructions.append(initial_request_instruction)

            pm_message = lc.invoke(
                            chat_model= self.pm_llm,
                            user_role= pm_role,
                            conversation= conversation,
                            instructions= instructions
                        )
            misc.print_message(pm_message)
            front_client.post_new_metier_or_po_answer(pm_message)

            if pm_message.content.__contains__("[FIN_PM_ASSIST]"):
                pm_answer = front_client.wait_metier_answer_validation_and_get() 
                continue
                
            # Ask business with latest PM questions & run:
            business_message = lc.invoke(
                                chat_model= self.business_llm,
                                user_role= business_role,
                                conversation= conversation,
                                instructions= [self.business_instructions, initial_request_instruction]
                            )
            misc.print_message(business_message)            
            front_client.post_new_metier_or_po_answer(business_message)        
            business_answer = front_client.wait_metier_answer_validation_and_get()
            # update last conversation message if changed by the user
            if conversation.messages[-1].content != business_answer:
                conversation.messages[-1].content = business_answer            

    def create_po_us_and_usecases(self, conversation: Conversation):
        pm_business_thread_json_str = conversation.get_all_messages_as_json()
        po_question = file.get_as_str("po_message_for_us_and_usecases_creation.txt").format(pm_business_thread_json= pm_business_thread_json_str)
        po_message = lc.invoke(self.po_llm, "", po_question, Conversation())
        misc.print_message(po_message)
    
    async def create_qa_acceptance_tests_async(self):        
        us_and_usecases_json_str = ai.get_last_answer(self.po_llm)
        return await self.write_qa_acceptance_tests_from_us_json_async(us_and_usecases_json_str)

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

    def save_po_us_and_usecases(self):
        us_and_usecases_json_str = ai.get_last_answer(self.po_llm)
        us_and_usecases_json = misc.extract_json_from_text(us_and_usecases_json_str)
        # print(f"new windows lines: {us_and_usecases_json.count('\r\n')}")
        # print(f"new lines: {us_and_usecases_json.count('\n')}")
        #print(f"caridge return: {us_and_usecases_json.count('\r')}")
        front_client.post_po_us_and_usecases(us_and_usecases_json)
        us_and_usecases_json_str = misc.json_to_str(us_and_usecases_json)
        file.write_file(us_and_usecases_json_str, misc.sharedFolder, "user_story.json")

    def save_metier_po_exchange(self, conversation: Conversation):
        messages_json = conversation.get_all_messages_as_json()
        messages_str = misc.json_to_str(messages_json)
        file.write_file(messages_str, misc.sharedFolder, "BusinessExpert_ProductOwner_Exchanges.json")
        
    def delete_all_outputs(self):
        file.delete_folder_contents(misc.sharedFolder)
        file.delete_all_files_with_extension("*.feature", "AcceptanceTests")
        file.delete_all_files_with_extension("*StepDefinitions.cs", "AcceptanceTests")
    
    # def create_check_end_assistant(self):
    #     self.check_end_assistant = lc.create_chat_langchain(
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
        
    def create_assistants(self):        
        self.model_gpt_35 = "gpt-3.5-turbo-16k" 
        self.model_gpt_40 = "gpt-4-0613"

        # Assistants creation
        self.business_llm = lc.create_chat_langchain(
             model= self.model_gpt_40,
            timeout_seconds= 100, 
            temperature= 0.1,
        )
        self.business_instructions= file.get_as_str("business_expert_assistant_instructions.txt")

        self.pm_instructions = file.get_as_str("pm_assistant_instructions.txt").format(max_exchanges_count= self.max_exchanges_count)
        self.pm_llm = lc.create_chat_langchain(
            model= self.model_gpt_40,
            timeout_seconds= 100, 
            temperature= 0.1
        )

        self.po_llm = lc.create_chat_langchain(
            model= self.model_gpt_40,
            timeout_seconds= 100, 
            temperature= 0.1,
        )
        self.po_instructions= file.get_as_str("po_us_assistant_instructions.txt")

        self.qa_assistant_set = lc.create_chat_langchain(
            model= self.model_gpt_40,
            timeout_seconds= 100, 
            temperature= 0.1,
        )
        self.qa_instructions= file.get_as_str("qa_assistant_instructions.txt")

    def print_assistants_ids(self):
        display.display_chat_infos("Métier", self.business_llm)
        display.display_chat_infos("PM", self.pm_llm)
        display.display_chat_infos("PO",  self.po_llm)
        display.display_chat_infos("QA",  self.qa_assistant_set)
        print("")

    # def dispose(self):
    #     try:
    #         ai.delete_assistant_set(self.pm_llm)
    #         ai.delete_assistant_set(self.business_llm)
    #         ai.delete_assistant_set(self.po_llm)
    #         ai.delete_assistant_set(self.qa_assistant_set)
    #         ai.delete_all_assistants()
    #     except Exception:
    #         pass

