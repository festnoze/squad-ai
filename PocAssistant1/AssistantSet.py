class AssistantSetIds:
    def __init__(self, assistant_id, thread_id, run_instructions):
        self.assistant_id = assistant_id
        self.thread_id = thread_id
        self.run_instructions = run_instructions

class AssistantSet:
    def __init__(self, assistant, thread, run_instructions, run = None, answer = None):
        self.assistant = assistant
        self.thread = thread
        self.run_instructions = run_instructions
        self.run = run
        self.answer = answer