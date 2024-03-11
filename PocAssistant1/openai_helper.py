import openai
import time
import uuid
from datetime import datetime, timedelta

from AssistantSet import AssistantSet, AssistantSetIds

class ai:    
    def create_full_assistant(model, instructions, run_instructions, message = None):
        assistant = ai.create_assistant(model, instructions)
        thread = ai.create_thread()
        if message:
            ai.add_message(thread.id, message)
        run = ai.create_run(assistant.id, thread.id, run_instructions)
        return AssistantSet(assistant, thread, run)

    def create_assistant(model, instructions, file_ids = None):
        return openai.beta.assistants.create(
            name= f"auto_assist_{str(uuid.uuid4())}",
            instructions= instructions,
            model=model,
            file_ids= file_ids
        )

    def create_thread():
        return openai.beta.threads.create()
    
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

    def create_run(assistant_id, thread_id, instructions):
        return openai.beta.threads.runs.create(
            assistant_id= assistant_id,
            thread_id= thread_id,
            instructions= instructions
        )
    
    def await_run_completed(assistant_set):
        sleep_interval = 2
        max_allowed_time = 40
        start_time = datetime.now()
        run_completed = False

        def has_allowed_time_elapsed():
            return start_time - datetime.now() > timedelta(seconds= max_allowed_time)
        
        # create a new 'run' each time
        assistant_set.run = ai.create_run(assistant_set.assistant.id, assistant_set.thread.id, assistant_set.run.instructions)

        while not run_completed:
            try:
                if assistant_set.run.completed_at is not None and assistant_set.run.completed_at > start_time.timestamp():
                    run_completed = True
                    return ai.get_last_answer(assistant_set)
                                
            except Exception as ex:
                run_completed = True
                return f"Error while waiting for the runner to respond: {ex.with_traceback}"

            ai.pause(sleep_interval)
            
            if not run_completed and has_allowed_time_elapsed():
                run_completed = True
                return f"Runner has timeout. Took more than: {max_allowed_time}s. to proceed"
            
    def get_last_answer(assistant_set):
        response = ""
        elapsed_time = assistant_set.run.completed_at - assistant_set.run.created_at
        formatted_elapsed_time = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))
        messages = openai.beta.threads.messages.list(thread_id= assistant_set.thread.id)
        index = 1
        for data in messages.data:
            #if data.role == "assistant":
                response += f"({index})- '{data.role}': "
                for content in data.content:
                    response += f"{content.text.value} - "
                response += "\n"
        #response = last_message.content[0].text.value
        return f"({formatted_elapsed_time}): {response}"
    
    def create_from_ids(assist_ids):
        return AssistantSet(
            assistant= openai.beta.assistants.retrieve(assist_ids.assistant_id),
            thread= openai.beta.threads.retrieve(assist_ids.thread_id),
            run= openai.beta.threads.runs.retrieve(
                run_id= assist_ids.run_id,
                thread_id= assist_ids.thread_id)
        )
    
    def create_new_thread_on_existing_assistant(assistant_id):
        assistants= openai.beta.assistants.retrieve(assistant_id),
        threads= ai.create_thread(),
        run= ai.create_run(assistant_id, threads[0].id, "")

        return AssistantSet(
            assistant= assistants[0],
            thread= threads[0],
            run= run
        )
    
    def pause(duration = None):        
        time.sleep(duration)
    
    def str_file(file_name):
        try:
            with open(file_name, 'r', encoding='utf-8') as file_reader:
                content = file_reader.read()
                return content
        except FileNotFoundError:
            print(f"file: {file_name} cannot be found.")
            return None
        except Exception as e:
            print(f"Error happends while reading file: {file_name}: {e}")
            return None

    
    def delete_assistant_set(assistant):
        openai.beta.assistants.delete(assistant_id= assistant.assistant.id)
        openai.beta.threads.delete(thread_id= assistant.thread.id)