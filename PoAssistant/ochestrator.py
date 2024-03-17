from openai_helper import ai
from misc import misc
from display_helper import display
from datetime import datetime
from file import file
from front_client import front_client

class assistants_ochestrator:
    check_end_assistant = None
    def __init__(self, request_message, max_exchanges_count):
        self.request_message = request_message
        self.max_exchanges_count = max_exchanges_count

    async def perform_workflow_async(self):
        # us = file.get_as_str("outputs\\MOA_MOE_exchanges.json")
        # front_client.post_po_us_and_usecases(moamoe)
        # return
        
        self.delete_all_outputs()
        front_client.delete_new_moe_moa_thread()
        
        self.do_moe_moa_exchanges()
        self.save_moe_moa_exchange()
    
        self.create_po_us_and_usecases()
        self.save_po_us_and_usecases()
        
        threads_ids = await self.create_qa_acceptance_tests_async()
        self.save_qa_acceptance_tests(threads_ids)

    def do_moe_moa_exchanges(self):
        self.moa_assistant_set.run_instructions += "Le besoin principal et le but à atteindre est : '{self.request_message}'."
        moa_response = self.request_message
        message_json = misc.get_message_as_json("MOA", moa_response, 0)
        front_client.post_new_answer_moe_moa(message_json)
        counter = 0

        while True:
            counter += 1
            if counter > self.max_exchanges_count:
                return
            
            # Pass the need to MOE or latest MOA answer & run:
            run_result = ai.add_message_and_run(self.moe_assistant_set, moa_response) 
            moe_response = ai.get_run_result(self.moe_assistant_set, run_result)            
            str_elapsed = ai.get_run_duration_str(self.moe_assistant_set.run)
            elapsed_seconds = ai.get_run_duration_str(self.moe_assistant_set.run)
            message_json = misc.get_message_as_json("MOE", moe_response, elapsed_seconds)
            front_client.post_new_answer_moe_moa(message_json)
            print(f"({str_elapsed}) MOE :\n{moe_response}\n")
            if self.need_for_stop(moe_response, run_result, True):
                return
            
            # Pass response to MOA & run:
            moa_message = f"Ci-après sont les questions du MOE auxquelles tu dois répondre : \n{moe_response}"
            run_result = ai.add_message_and_run(self.moa_assistant_set, moa_message)
            moa_response = ai.get_run_result(self.moa_assistant_set, run_result)
            str_elapsed = ai.get_run_duration_str(self.moa_assistant_set.run)            
            elapsed_seconds = ai.get_run_duration_str(self.moa_assistant_set.run)
            message_json = misc.get_message_as_json("MOA", moa_response, elapsed_seconds)
            front_client.post_new_answer_moe_moa(message_json)
            print(f"({str_elapsed}) MOA : \n{moa_response}\n")        

            if self.need_for_stop(moa_response, run_result, False):
                return

    def create_po_us_and_usecases(self):
        moe_moa_thread_json_str = ai.get_all_messages_as_json(self.moa_assistant_set)
        po_message = file.get_as_str("po_message_for_us_and_usecases_creation.txt").format(moe_moa_thread_json= moe_moa_thread_json_str)
        result = ai.add_message_and_run(self.po_assistant_set, po_message)
        if (result == ai.RunResult.SUCCESS):
            elapsed = ai.get_run_duration_str(self.moa_assistant_set.run)
            print(f"({elapsed}) PO: \n{ai.get_last_answer(self.po_assistant_set)}")
    
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
        elapsed = misc.get_elapsed_time_str(start_time.timestamp(), datetime.now().timestamp())
        print(f"({elapsed}) QA :\n")
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
        
    
    def need_for_stop(self, response, result, check_for_questions):
        # Handle the escape sentence from the MOE model
        if response.__contains__("[FIN_MOE_ASSIST]"):
            return True
        if check_for_questions and not self.has_questions(response):
            return True
        # if check_for_questions and not self.has_assistant_detect_question(response):
        #     return True
        if result != ai.RunResult.SUCCESS:
            return True
        # Ask user for stopping the discussion
        # doloop = input(">>> Taper 'Entrée' pour continuer ou n'importe quelle lettre pour arreter")
        # if doloop != "":
        #   return True
        return False
    
    
    def save_qa_acceptance_tests(self, threads_ids):
        i = 1
        for thread_id in threads_ids:
            content = misc.str_to_gherkin(ai.get_last_thread_answer(thread_id))
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
        file.write_file(us_and_usecases_json_str, "outputs", "user_story.json")

    def save_moe_moa_exchange(self):
        messages_json = ai.get_all_messages_as_json(self.moe_assistant_set)
        messages_str = misc.json_to_str(messages_json).replace("\"user\"", "\"MOA\"").replace("\"assistant\"", "\"MOE\"")
        file.write_file(messages_str, "outputs", "MOA_MOE_exchanges.json")
        
    def delete_all_outputs(self):
        file.delete_folder("outputs")
        file.delete_files_with_extension("feature", "AcceptanceTests")

    
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
        self.moa_assistant_set = ai.create_assistant_set(
            model= self.model_gpt_40, 
            instructions= file.get_as_str("moa_assistant_instructions.txt"),
            run_instructions = "",#file.get_as_str("moa_run_instructions.txt"),
            timeout_seconds= 50
        )
        moe_assistant_instructions = file.get_as_str("moe_assistant_instructions.txt").format(max_exchanges_count= self.max_exchanges_count)
        self.moe_assistant_set = ai.create_assistant_set(
            model= self.model_gpt_40, 
            instructions= moe_assistant_instructions,
            run_instructions = "",#file.get_as_str("moe_run_instructions.txt"),
            timeout_seconds= 50
        )
        self.po_assistant_set = ai.create_assistant_set(
            model= self.model_gpt_40, 
            instructions= file.get_as_str("po_assistant_instructions.txt"),
            run_instructions = "",
            timeout_seconds= 100
        )
        self.qa_assistant_set = ai.create_assistant_set(
                model= self.model_gpt_35, 
                instructions= file.get_as_str("qa_assistant_instructions.txt"),
                run_instructions = "",
                timeout_seconds= 25
        )

    def print_assistants_ids(self):
        display.display_ids("MOA", self.moa_assistant_set)
        display.display_ids("MOE", self.moe_assistant_set)
        display.display_ids("PO",  self.po_assistant_set)
        display.display_ids("QA",  self.qa_assistant_set)
        print("")

    def dispose(self):
        try:
            ai.delete_assistant_set(self.moe_assistant_set)
            ai.delete_assistant_set(self.moa_assistant_set)
            ai.delete_assistant_set(self.po_assistant_set)
            ai.delete_assistant_set(self.qa_assistant_set)
            ai.delete_all_assistants()
        except Exception:
            pass

