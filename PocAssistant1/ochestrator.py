from openai_helper import ai
from misc import misc

class assistants_ochestrator:
    check_end_assistant = None
    def __init__(self, request_message, moe_assistant_set, moa_assistant_set, po_assistant, max_exchanges_count):
        self.request_message = request_message
        self.moe_assistant_set = moe_assistant_set
        self.moa_assistant_set = moa_assistant_set
        self.po_assistant = po_assistant
        self.max_exchanges_count = max_exchanges_count

        #self.create_check_end_assistant()
        print(f"GOAL : {request_message}")
        self.do_moe_moa_exchanges(request_message)
        self.do_po_us_redaction()

    def do_moe_moa_exchanges(self, request_message):
        self.moa_assistant_set.run_instructions += "Le besoin principal et le but à atteindre est : '{request_message}'."
        moe_message = request_message
        counter = 0

        while True:
            counter += 1
            if counter > self.max_exchanges_count:
                return
            
            # Pass the need to MOE or latest MOA answer & run:
            run_result = ai.add_message_and_run(self.moe_assistant_set, moe_message) 
            #all_moe_messages = ai.get_run_result(moe_assistant_set, result, True)
            moe_response = ai.get_run_result(self.moe_assistant_set, run_result)
            
            elapsed = misc.get_elapsed_time(self.moe_assistant_set.run.created_at, self.moe_assistant_set.run.completed_at)
            print(f"({elapsed}) MOE :\n{moe_response}\n")

            if self.need_for_stop(moe_response, run_result, True):
                return
            
            # Pass response to MOA & run:
            moa_message = f"Ci-après sont les questions du MOE auxquelles tu dois répondre : \n{moe_response}"
            run_result = ai.add_message_and_run(self.moa_assistant_set, moa_message)
            moa_response = ai.get_run_result(self.moa_assistant_set, run_result)
            elapsed = ai.get_run_duration(self.moa_assistant_set.run)
            print(f"({elapsed}) MOA : \n{moa_response}\n")
            moe_message = moa_response

            if self.need_for_stop(moa_response, run_result, False):
                return

    def do_po_us_redaction(self):
        moe_moa_thread_json_str = ai.get_all_messages_as_json(self.moa_assistant_set)
        po_message = misc.get_str_file("po_message_for_us_and_usecases_creation.txt").format(moe_moa_thread_json= moe_moa_thread_json_str)
        result = ai.add_message_and_run(self.po_assistant, po_message)
        if (result == ai.RunResult.SUCCESS):
            elapsed = ai.get_run_duration(self.moa_assistant_set.run)
            print(f"({elapsed}) PO: \n{ai.get_last_answer(self.po_assistant)}")
    
    def do_qa_acceptance_tests_redaction(self):
        return
    
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
    
    def create_check_end_assistant(self):
        self.check_end_assistant = ai.create_assistant_set(
            model= "gpt-3.5-turbo-16k",
            instructions="Tu es un expert en analyse de phrases, et tu dois toujours répondre uniquement par oui ou non",
            run_instructions= ""
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


