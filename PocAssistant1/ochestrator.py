import asyncio
from openai_helper import ai
from misc import misc
from display_helper import display

class assistants_ochestrator:
    check_end_assistant = None
    def __init__(self, request_message, max_exchanges_count):
        self.request_message = request_message
        self.max_exchanges_count = max_exchanges_count

    async def init_assistants_async(self):        
        model_gpt_35 = "gpt-3.5-turbo-16k" 
        model_gpt_40 = "gpt-4-turbo-preview"

        # Assistants creation
        self.moa_assistant_set = await ai.create_assistant_set_async(
            model= model_gpt_35, 
            instructions= misc.get_str_file("moa_assistant_instructions.txt"),
            run_instructions = ""#misc.get_str_file("moa_run_instructions.txt")
        )
        moe_assistant_instructions = misc.get_str_file("moe_assistant_instructions.txt").format(max_exchanges_count= self.max_exchanges_count)
        self.moe_assistant_set = await ai.create_assistant_set_async(
            model= model_gpt_35, 
            instructions= moe_assistant_instructions,
            run_instructions = ""#misc.get_str_file("moe_run_instructions.txt")
        )
        self.po_assistant_set = await ai.create_assistant_set_async(
            model= model_gpt_40, 
            instructions= misc.get_str_file("po_assistant_instructions.txt"),
            run_instructions = ""
        )
        self.qa_assistant_set = await ai.create_assistant_set_async(
            model= model_gpt_35, 
            instructions= misc.get_str_file("qa_assistant_instructions.txt"),
            run_instructions = ""
        )

    def print_assistants_ids(self):
        display.display_ids("MOA", self.moa_assistant_set)
        display.display_ids("MOE", self.moe_assistant_set)
        display.display_ids("PO",  self.po_assistant_set)
        display.display_ids("QA",  self.qa_assistant_set)
        print("")

    async def run_async(self):
        #self.create_check_end_assistant()
        print(f"GOAL : {self.request_message}")
        await self.do_moe_moa_exchanges_async()
        await self.write_po_us_and_usecases_async()
        await self.write_qa_acceptance_tests_async()

    async def do_moe_moa_exchanges_async(self):
        self.moa_assistant_set.run_instructions += "Le besoin principal et le but à atteindre est : '{self.request_message}'."
        moe_message = self.request_message
        counter = 0

        while True:
            counter += 1
            if counter > self.max_exchanges_count:
                return
            
            # Pass the need to MOE or latest MOA answer & run:
            run_result = await ai.add_message_and_run_async(self.moe_assistant_set, moe_message) 
            #all_moe_messages = ai.get_run_result(moe_assistant_set, result, True)
            moe_response = ai.get_run_result(self.moe_assistant_set, run_result)
            
            elapsed = misc.get_elapsed_time(self.moe_assistant_set.run.created_at, self.moe_assistant_set.run.completed_at)
            print(f"({elapsed}) MOE :\n{moe_response}\n")

            if await self.need_for_stop_async(moe_response, run_result, True):
                return
            
            # Pass response to MOA & run:
            moa_message = f"Ci-après sont les questions du MOE auxquelles tu dois répondre : \n{moe_response}"
            run_result = await ai.add_message_and_run_async(self.moa_assistant_set, moa_message)
            moa_response = ai.get_run_result(self.moa_assistant_set, run_result)
            elapsed = ai.get_run_duration(self.moa_assistant_set.run)
            print(f"({elapsed}) MOA : \n{moa_response}\n")
            moe_message = moa_response

            if await self.need_for_stop_async(moa_response, run_result, False):
                return

    async def write_po_us_and_usecases_async(self):
        moe_moa_thread_json_str = ai.get_all_messages_as_json(self.moa_assistant_set)
        po_message = misc.get_str_file("po_message_for_us_and_usecases_creation.txt").format(moe_moa_thread_json= moe_moa_thread_json_str)
        result = await ai.add_message_and_run_async(self.po_assistant_set, po_message)
        if (result == ai.RunResult.SUCCESS):
            elapsed = ai.get_run_duration(self.moa_assistant_set.run)
            print(f"({elapsed}) PO: \n{ai.get_last_answer(self.po_assistant_set)}")
    
    async def write_qa_acceptance_tests_async(self):
        us_and_usecases_json_str = ai.get_last_answer(self.po_assistant_set)
        us_and_usecases_json = misc.str_to_json(us_and_usecases_json_str)
        user_story = us_and_usecases_json.us_desc
        threads_ids_and_qa_acceptance_test_runs = []
        for usecase_json in us_and_usecases_json.use_cases:
            threads_ids_and_qa_acceptance_test_runs.append( self.write_qa_acceptance_test_async(usecase_json))
        qa_acceptance_test_runs = [element[1] for element in threads_ids_and_qa_acceptance_test_runs]
        results = await asyncio.gather(qa_acceptance_test_runs)
        for written_qa_acceptance_test in threads_ids_and_qa_acceptance_test_runs:
            thread_id = written_qa_acceptance_test[0]
            result = written_qa_acceptance_test[1]
            if (result == ai.RunResult.SUCCESS):
                print(f"\n{ai.get_last_thread_answer(thread_id)}")


    async def write_qa_acceptance_test_async(self, usecase_json):
        qa_init_message = misc.get_str_file("qa_message_for_acceptance_tests.txt")
        qa_message = qa_init_message.format(use_case= usecase_json.uc_desc).format(acceptance_criteria= misc.json_array_to_bullet_list_str(usecase_json.acceptance_criteria))
        specific_thread = ai.add_new_thread_message(qa_message)
        return specific_thread.id, ai.run_async(self.qa_assistant_set, specific_thread.id)
        if (result == ai.RunResult.SUCCESS):
            elapsed = ai.get_run_duration(self.moa_assistant_set.run)
            print(f"({elapsed}) QA: \n{ai.get_last_answer(self.po_assistant_set)}")
    
    async def need_for_stop_async(self, response, result, check_for_questions):
        # Handle the escape sentence from the MOE model
        if response.__contains__("[FIN_MOE_ASSIST]"):
            return True
        if check_for_questions and not self.has_questions(response):
            return True
        # if check_for_questions and not await self.has_assistant_detect_question(response):
        #     return True
        if result != ai.RunResult.SUCCESS:
            return True
        # Ask user for stopping the discussion
        # doloop = input(">>> Taper 'Entrée' pour continuer ou n'importe quelle lettre pour arreter")
        # if doloop != "":
        #   return True
        return False
    
    def create_check_end_assistant(self):
        self.check_end_assistant = ai.create_assistant_set_async(
            model= "gpt-3.5-turbo-16k",
            instructions="Tu es un expert en analyse de phrases, et tu dois toujours répondre uniquement par oui ou non",
            run_instructions= ""
        )

    def has_questions(self, message):
        return message.__contains__("?") or  message.__contains__("merci")

    #don't work proprely
    async def has_assistant_detect_question_async(self, message):
        message = f"Est ce que le texte suivant contient une ou plusieurs questions: \n'{message}'"
        result = await ai.add_message_and_run_async(self.check_end_assistant, message)
        if result != ai.RunResult.SUCCESS:
            return False
        answer = ai.get_last_answer(self.check_end_assistant)
        if answer.__contains__("oui"):
            return True
        return False

    def dispose(self):
        try:
            ai.delete_assistant_set(self.moe_assistant_set)
            ai.delete_assistant_set(self.moa_assistant_set)
            ai.delete_assistant_set(self.po_assistant_set)
            ai.delete_assistant_set(self.qa_assistant_set)
            #ai.delete_all_assistants()
        except Exception:
            pass

