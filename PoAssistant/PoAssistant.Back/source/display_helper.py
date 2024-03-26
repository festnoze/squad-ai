import os

class display:
    def display_assistant_ids(title, assistant_set):
        print(f"{title}:")
        print(f"• assistant id: '{assistant_set.assistant.id}'")
        print(f"• thread id:    '{assistant_set.thread.id}'")
        print(f"----------------------------------------------")

    def display_chat_infos(title, chat_llm):
        print(f"{title}:")
        print(f"• chat name: '{chat_llm.name}'")
        print(f"----------------------------------------------")
        