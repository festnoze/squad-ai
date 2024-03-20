from openai_helper import ai
from misc import misc
from display_helper import display
from datetime import datetime
from file import file
from front_client import front_client

class assistants_ochestrator:
    check_end_assistant = None
    def __init__(self, max_exchanges_count):
        self.max_exchanges_count = max_exchanges_count

    async def perform_workflow_async(self):  
        self.delete_all_outputs()
        front_client.ping_front_until_responding()
        front_client.delete_all_metier_po_thread()

        self.request_message = misc.wait_brief_file_creation_and_return()
        print(f"Description initiale de l'objectif : {self.request_message}")
                
        self.do_metier_po_exchanges()
        self.save_metier_po_exchange()
    
        self.create_po_us_and_usecases()
        self.save_po_us_and_usecases()
        
        threads_ids = await self.create_qa_acceptance_tests_async()
        self.save_qa_acceptance_tests(threads_ids)

    def do_metier_po_exchanges(self):
        self.business_assistant_set.run_instructions += "Le besoin principal et le but à atteindre est : '{self.request_message}'."
        business_response = self.request_message
        message_json = misc.get_message_as_json("Métier", business_response, 0)
        counter = 0

        while True:
            counter += 1
            if counter > self.max_exchanges_count:
                return
            
            # Pass to PO latest business expert's answer (or the need / brief on first) & run:
            run_result = ai.add_message_and_run(self.po_moe_assistant_set, business_response) 
            po_moe_response = ai.get_run_result(self.po_moe_assistant_set, run_result)
            elapsed_seconds = ai.get_run_duration_seconds(self.po_moe_assistant_set.run)
            message_json = misc.get_message_as_json("PO", po_moe_response, elapsed_seconds)
            print(f"({elapsed_seconds}s.) PO :\n{po_moe_response}\n")

            front_client.post_new_metier_or_po_answer(message_json)

            if self.need_for_stop(po_moe_response, run_result, True):
                return
            
            # Pass to business expert latest PO questions & run:
            moa_message = f"Ci-après sont les questions du PO auxquelles tu dois répondre : \n{po_moe_response}"
            run_result = ai.add_message_and_run(self.business_assistant_set, moa_message)
            business_response = ai.get_run_result(self.business_assistant_set, run_result)      
            elapsed_seconds = ai.get_run_duration_seconds(self.business_assistant_set.run)
            message_json = misc.get_message_as_json("Métier", business_response, elapsed_seconds)
            print(f"({elapsed_seconds}s.) Métier : \n{business_response}\n") 
            
            front_client.post_new_metier_or_po_answer(message_json)
            
            business_response = misc.wait_metier_answer_file_creation_and_return()       

            # if self.need_for_stop(business_response, run_result, False):
            #     return

    def create_po_us_and_usecases(self):
        po_business_thread_json_str = ai.get_all_messages_as_json(self.business_assistant_set)
        po_message = file.get_as_str("po_message_for_us_and_usecases_creation.txt").format(po_business_thread_json= po_business_thread_json_str)
        result = ai.add_message_and_run(self.po_assistant_set, po_message)
        if (result == ai.RunResult.SUCCESS):
            elapsed = ai.get_run_duration_seconds(self.business_assistant_set.run)
            print(f"({elapsed}s.) PO: \n{ai.get_last_answer(self.po_assistant_set)}")
    
    async def create_qa_acceptance_tests_async(self):        
        us_and_usecases_json_str = ai.get_last_answer(self.po_assistant_set)
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
        
    
    def need_for_stop(self, po_response, result, check_for_questions):
        if po_response.__contains__("[FIN_PO_ASSIST]"):
            business_response = misc.wait_metier_answer_file_creation_and_return() 
            if business_response.__contains__("[ENDS_EXCHANGE]"):
                return True
            else:
                return False
    
    
    def save_qa_acceptance_tests(self, threads_ids):
        i = 1
        for thread_id in threads_ids:
            content = misc.str_to_gherkin(ai.get_last_thread_answer(thread_id))
            content = misc.output_parser_gherkin(content)
            file.write_file(content, "AcceptanceTests", f"use_case{i}.feature")
            i += 1

    def save_po_us_and_usecases(self):
        us_and_usecases_json_str = ai.get_last_answer(self.po_assistant_set)
        us_and_usecases_json = misc.extract_json_from_text(us_and_usecases_json_str)
        # print(f"new windows lines: {us_and_usecases_json.count('\r\n')}")
        # print(f"new lines: {us_and_usecases_json.count('\n')}")
        #print(f"caridge return: {us_and_usecases_json.count('\r')}")
        front_client.post_po_us_and_usecases(us_and_usecases_json)
        us_and_usecases_json_str = misc.json_to_str(us_and_usecases_json)
        file.write_file(us_and_usecases_json_str, misc.sharedFolder, "user_story.json")

    def save_metier_po_exchange(self):
        messages_json = ai.get_all_messages_as_json(self.po_moe_assistant_set)
        messages_str = misc.json_to_str(messages_json).replace("\"user\"", "\"Métier\"").replace("\"assistant\"", "\"PO\"")
        file.write_file(messages_str, misc.sharedFolder, "BusinessExpert_ProductOwner_Exchanges.json")
        
    def delete_all_outputs(self):
        file.delete_folder_contents(misc.sharedFolder)
        file.delete_all_files_with_extension("*.feature", "AcceptanceTests")
        file.delete_all_files_with_extension("*StepDefinitions.cs", "AcceptanceTests")
        file.delete_file(misc.brief_file_path)
        file.delete_file(misc.metier_answer_file_path)

    
    def create_check_end_assistant(self):
        self.check_end_assistant = ai.create_assistant_set(
            model= "gpt-3.5-turbo-16k",
            instructions="Tu es un expert en analyse de phrases, et tu dois toujours répondre uniquement par oui ou non",
            run_instructions= "",
            timeout_seconds= 20
        )

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
        self.model_gpt_40 = "gpt-4-turbo-preview"

        # Assistants creation
        self.business_assistant_set = ai.create_assistant_set(
            model= self.model_gpt_40, 
            instructions= file.get_as_str("business_expert_assistant_instructions.txt"),
            run_instructions = "",#file.get_as_str("moa_run_instructions.txt"),
            timeout_seconds= 100
        )
        po_moe_assistant_instructions = file.get_as_str("po_moe_assistant_instructions.txt").format(max_exchanges_count= self.max_exchanges_count)
        self.po_moe_assistant_set = ai.create_assistant_set(
            model= self.model_gpt_40, 
            instructions= po_moe_assistant_instructions,
            run_instructions = "",
            timeout_seconds= 50
        )
        self.po_assistant_set = ai.create_assistant_set(
            model= self.model_gpt_40, 
            instructions= file.get_as_str("po_us_assistant_instructions.txt"),
            run_instructions = "",
            timeout_seconds= 100
        )
        self.qa_assistant_set = ai.create_assistant_set(
                model= self.model_gpt_35, 
                instructions= file.get_as_str("qa_assistant_instructions.txt"),
                run_instructions = "",
                timeout_seconds= 45
        )

    def print_assistants_ids(self):
        display.display_ids("Métier", self.business_assistant_set)
        display.display_ids("PO(MOE)", self.po_moe_assistant_set)
        display.display_ids("PO(US)",  self.po_assistant_set)
        display.display_ids("QA",  self.qa_assistant_set)
        print("")

    def dispose(self):
        try:
            ai.delete_assistant_set(self.po_moe_assistant_set)
            ai.delete_assistant_set(self.business_assistant_set)
            ai.delete_assistant_set(self.po_assistant_set)
            ai.delete_assistant_set(self.qa_assistant_set)
            ai.delete_all_assistants()
        except Exception:
            pass

