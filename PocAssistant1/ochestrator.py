from openai_helper import ai
from misc import misc

class assistants_ochestrator:
    def __init__(self, request_message, moe_assistant_set, moa_assistant_set):
        self.request_message = request_message
        self.moe_assistant_set = moe_assistant_set
        self.moa_assistant_set = moa_assistant_set

        moa_message = request_message
        moa_assistant_set.run_instructions += "Le besoin principal et le but à atteindre est : '{moa_message}'."
        print(f"GOAL : {moa_message}")

        while True:
            # Pass the need to MOE & run:
            moe_response = ai.add_message_and_run(moe_assistant_set, moa_message)  

            # Handle the escape sentence from the MOE model
            if moe_response.__contains__("[FIN_MOE_ASSIST]"):
                return
            
            elapsed = misc.get_elapsed_time( moe_assistant_set.run.created_at, moe_assistant_set.run.completed_at)
            print(f"({elapsed}) MOE : {moe_response}")

            doloop = input("----- Pour continuer, tapez: 'y' -----")
            if doloop != "y":
                return
            
            # Pass response to MOA & run:
            moa_message = f"""
            Ci-après sont les questions du MOE auxquelles tu dois répondre :
            {moe_response}"""
            moa_response = ai.add_message_and_run(moa_assistant_set, moa_message)
            elapsed = misc.get_elapsed_time( moa_assistant_set.run.created_at, moa_assistant_set.run.completed_at)
            print(f"({elapsed}) MOA : {moa_response}")

            doloop = input("----- Pour continuer, tapez: 'y' -----")
            if doloop != "y":
                return

