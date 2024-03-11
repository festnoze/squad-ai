import os

class display:
    def display_ids(title, assistant_set):
        print(f"{title}:")
        print(f"• assistant id: '{assistant_set.assistant.id}'")
        print(f"• thread id:    '{assistant_set.thread.id}'")
        print(f"• run id:       '{assistant_set.run.id}'")
        print(f"----------------------------------------------")
        print(f"")