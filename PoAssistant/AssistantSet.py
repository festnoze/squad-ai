class AssistantSetIds:
    def __init__(self, assistant_id, thread_id, run_instructions, timeout_seconds = None):
        self.assistant_id = assistant_id
        self.thread_id = thread_id
        self.run_instructions = run_instructions
        self.timeout_seconds = timeout_seconds

class AssistantSet:
    def __init__(self, assistant, thread, run_instructions, timeout_seconds = None, run = None):
        self.assistant = assistant
        self.thread = thread
        self.run_instructions = run_instructions
        self.timeout_seconds = timeout_seconds
        self.run = run