import openai
import uuid
import json
from datetime import datetime, timedelta
from enum import Enum
# internal import
from misc import misc
from AssistantSet import AssistantSet

class ai:    
    def max_allowed_run_seconds(assistant_set):
        model = assistant_set.assistant.model
        #Set timeout depending on seleted model
        if model.__contains__("gpt-4"):
            return 120
        else:
            return 40

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
        openai.beta.threads.messages.create(
            thread_id= thread_id,
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
        start_time = datetime.now()

        def has_allowed_time_elapsed(assistant_set):
            return datetime.now() - start_time > timedelta(seconds= ai.max_allowed_run_seconds(assistant_set))
        
        # create a new 'run' each time
        assistant_set.run = ai.create_run(assistant_set)

        while assistant_set.run.status != "completed":
            assistant_set.run = openai.beta.threads.runs.retrieve(run_id= assistant_set.run.id, thread_id= assistant_set.thread.id)
            try:
                if assistant_set.run.completed_at:
                    return ai.RunResult.SUCCESS 
                                
            except Exception as ex:
                return ai.RunResult.ERROR

            misc.pause(sleep_interval)
            
            if assistant_set.run.status != "completed" and has_allowed_time_elapsed(assistant_set):
                return ai.RunResult.TIMEOUT
    
    class RunResult(Enum):
        SUCCESS = 1
        ONGOING = 0,
        ERROR = -1
        TIMEOUT = -2

    def get_run_result(assistant_set, result, get_all_messages = False):
        if result == ai.RunResult.SUCCESS:
            if get_all_messages:
                return ai.get_all_messages(assistant_set)
            else:
                return ai.get_last_answer(assistant_set)
            
        if result == ai.RunResult.ERROR:
            return  f"Error while waiting for the runner to respond" #: {ex.with_traceback}"
        
        if result == ai.RunResult.TIMEOUT:
            return f"Runner has timeout. Took more than: {ai.max_allowed_run_seconds(assistant_set)}s. to proceed"
            
    def get_last_answer(assistant_set):
        messages = openai.beta.threads.messages.list(thread_id= assistant_set.thread.id)
        return messages.data[0].content[0].text.value
    
    def get_all_messages(assistant_set):
        messages = openai.beta.threads.messages.list(thread_id= assistant_set.thread.id)
        response = ""
        index = 1
        for data in messages.data:
            #if data.role == "assistant":
                response += f"(data {index})- '{data.role}':\n"
                index += 1
                for content in data.content:
                    response += f"• {content.text.value}\n"
                response += "\n"
        #response = last_message.content[0].text.value
        return f"{response}"

    def get_all_messages_as_json(assistant_set):
        messages = openai.beta.threads.messages.list(thread_id= assistant_set.thread.id)
        json = []
        for data in messages.data:
            message_dict = {
                "role": data.role,
                "content": {"text": data.content[0].text.value}
                #to rather handle multiple contents: 
                #"content": [{"text": content.text.value} for content in data.content]
            }
            json.append(message_dict)
    
        result = str(json) #json.dumps(json, indent= 4)
        return result
        
    def get_run_duration(run):
        return misc.get_elapsed_time(run.created_at, run.completed_at)
    
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