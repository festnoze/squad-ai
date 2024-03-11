class AssistantSetIds:
    def __init__(self, assistant_id, thread_id, run_id):
        self.assistant_id = assistant_id
        self.thread_id = thread_id
        self.run_id = run_id

class AssistantSet:
    def __init__(self, assistant, thread, run):
        self.assistant = assistant
        self.thread = thread
        self.run = run