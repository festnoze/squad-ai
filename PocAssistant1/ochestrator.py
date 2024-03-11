from openai_helper import ai

class assistants_ochestrator:
    def __init__(self, request_message, moe_assistant_set, moa_assistant_set):
        self.initial_message = request_message
        self.moe_assistant_set = moe_assistant_set
        self.moa_assistant_set = moa_assistant_set

        # Pass initial message to MOE & run:
        initial_message = "présente toi et demande moi d'exprimer mon besoin fonctionnel"
        ai.add_message(moe_assistant_set.thread.id, initial_message)
        moe_response = ai.await_run_completed(moe_assistant_set)
        print(f"MOE response: {moe_response}")

        # Pass message containing the initial need to MOE & run:
        ai.add_message(moe_assistant_set.thread.id, request_message)
        moe_response = ai.await_run_completed(moe_assistant_set)
        print(f"MOE response: {moe_response}")

        # # Pass response to MOA & run:
        # moa_initial_message = f"""
        # The global goal is :'{initial_message}'.
        # Hereinafter are the MOE questions to be answered:
        # {moe_response}"""
        # moa_response = ai.add_message(moa_assistant.thread.id, moa_initial_message)
        # print(f"MOA: {moa_response}")
