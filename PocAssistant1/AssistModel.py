import openai

class AssistantIdsModel:
    def __init__(self, assistant_id, thread_id, run_id):
        self.assistant_id = assistant_id
        self.thread_id = thread_id
        self.run_id = run_id

class AssistantModel:
    def __init__(self, assistant, thread, run):
        self.assistant = assistant
        self.thread = thread
        self.run = run
    
    def create_from_ids(assist_ids):
        return AssistantModel(
            assistant= openai.beta.assistants.retrieve(assist_ids.assistant_id),
            thread= openai.beta.threads.retrieve(assist_ids.thread_id),
            run= openai.beta.threads.runs.retrieve(
                run_id= assist_ids.run_id,
                thread_id= assist_ids.thread_id)
        )