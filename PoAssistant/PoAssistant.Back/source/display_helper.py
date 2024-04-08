class display:
    def display_assistant_ids(title, assistant_set):
        print(f"{title}:")
        print(f"• assistant id: '{assistant_set.assistant.id}'")
        print(f"• thread id:    '{assistant_set.thread.id}'")
        print(f"----------------------------------------------")

    def display_llm_infos(llm):
        model_name = getattr(llm, 'model_name', None)
        model = getattr(llm, 'model', None)

        if model_name:
            print(f"• LLM model: '{model_name}' & name: '{llm.name}'")
        elif model:
            print(f"• LLM model: '{model}' & name: '{llm.name}'")
        else:
            print(f"• LLM model: '{llm.name}'")
        print(f"----------------------------------------------")
        print("")
        