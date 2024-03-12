import openai
import uuid
from datetime import datetime, timedelta
from misc import misc
from AssistantSet import AssistantSet

class ai:    
    def create_assistant_set(model, instructions, run_instructions, message = None):
        assistant = ai.create_assistant(model, instructions)
        thread = ai.create_thread()        
        assistant_set = AssistantSet(assistant, thread, run_instructions)
        if message:
            assistant_set.answer = ai.add_message_and_run(assistant_set)
        return assistant_set

    def create_assistant(model, instructions, file_ids = None):
        return openai.beta.assistants.create(
            name= f"auto_assist_{str(uuid.uuid4())}",
            instructions= instructions,
            model=model,
            file_ids= file_ids
        )

    def create_thread():
        return openai.beta.threads.create()
    
    def add_message_and_run(assistant_set, message):
        ai.add_message(assistant_set.thread.id, message)
        return ai.run(assistant_set)
        
    # Add a new user's message to the thread
    def add_message(thread_id, message):
        if not message: 
            return
        thread = openai.beta.threads.retrieve(thread_id= thread_id)
        openai.beta.threads.messages.create(
            thread_id= thread.id,
            role= "user",
            content= message
        )

    def create_run(assistant_set):
        return openai.beta.threads.runs.create(
            assistant_id= assistant_set.assistant.id,  
            thread_id= assistant_set.thread.id,
            instructions= assistant_set.run_instructions
        )
    
    def run(assistant_set):
        sleep_interval = 1
        max_allowed_time = 20
        start_time = datetime.now()

        def has_allowed_time_elapsed():
            return datetime.now() - start_time > timedelta(seconds= max_allowed_time)
        
        # create a new 'run' each time
        assistant_set.run = ai.create_run(assistant_set)

        while assistant_set.run.status != "completed":
            assistant_set.run = openai.beta.threads.runs.retrieve(run_id= assistant_set.run.id, thread_id= assistant_set.thread.id)
            try:
                if assistant_set.run.completed_at:
                    return ai.get_last_answer(assistant_set)
                                
            except Exception as ex:
                return f"Error while waiting for the runner to respond: {ex.with_traceback}"

            misc.pause(sleep_interval)
            
            if assistant_set.run.status != "completed" and has_allowed_time_elapsed():
                return f"Runner has timeout. Took more than: {max_allowed_time}s. to proceed"
            
    def get_last_answer(assistant_set):
        messages = openai.beta.threads.messages.list(thread_id= assistant_set.thread.id)
        return messages.data[0].content[0].text.value
    
    def get_all_messages(assistant_set):
        messages = openai.beta.threads.messages.list(thread_id= assistant_set.thread.id)
        for data in messages.data:
            

    
    def create_from_ids(assist_ids):
        return AssistantSet(
            assistant= openai.beta.assistants.retrieve(assist_ids.assistant_id),
            thread= openai.beta.threads.retrieve(assist_ids.thread_id),
            run_instructions= assist_ids.run_instructions
        )
            
    def delete_assistant_set(assistant):
        openai.beta.assistants.delete(assistant_id= assistant.assistant.id)
        openai.beta.threads.delete(thread_id= assistant.thread.id)

    def delete_all_assistants():
        assistants_ids_str = misc.get_str_file("assistants_to_delete.txt")
        assistants_ids_str_split = assistants_ids_str.split('\n')
        assistants_ids_list = [line.strip() for line in assistants_ids_str_split if line.strip()] # remove empty lines
        for assistant_id in assistants_ids_list:
            openai.beta.assistants.delete(assistant_id= assistant_id)

    def print_models():
        models = openai.models.list()
        for model in models:
            print(model.id)