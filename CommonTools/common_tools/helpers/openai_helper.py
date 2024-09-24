import time
import openai
import uuid
from datetime import datetime, timedelta
from enum import Enum
import concurrent.futures
import asyncio
# internal import
from common_tools.helpers.misc import misc

class ai:
    timeout_tag = "[LLM_REQUEST_TIMEOUT]"

    def max_allowed_run_seconds(assistant_set):
        return assistant_set.timeout_seconds

    def create_assistant(model, instructions, file_ids = None):
        return openai.beta.assistants.create(
            name= f"auto_assist_{str(uuid.uuid4())}",
            instructions= instructions,
            model=model,
            file_ids= file_ids
        )

    def create_thread():
        return openai.beta.threads.create()
    
    def add_new_thread_message(message):
        new_thread = ai.create_thread()
        ai.add_message(new_thread.id, message)
        return new_thread
    
    def add_message_and_run(assistant_set, message, run_instructions = None):
        ai.add_message(assistant_set.thread.id, message)
        return ai.run(assistant_set, None, run_instructions)         
    
    # Add a new user's message to the thread
    def add_message(thread_id, message):
        if not message: 
            return
        openai.beta.threads.messages.create(
            thread_id= thread_id,
            role= "user",
            content= message
        )

    def create_run(assistant_set, specific_thread_id = None, run_instructions = None):
        return openai.beta.threads.runs.create(
            assistant_id= assistant_set.assistant.id,  
            thread_id= specific_thread_id if specific_thread_id else assistant_set.thread.id,
            instructions= run_instructions if run_instructions else assistant_set.run_instructions
        )

    def has_allowed_time_elapsed(assistant_set, start_time):
        return datetime.now() - start_time > timedelta(seconds= ai.max_allowed_run_seconds(assistant_set))
    
    def run(assistant_set, specific_thread_id = None, run_instructions = None):
        sleep_interval = 2
        start_time = datetime.now()
        try:
            # create a new 'run' each time
            run = ai.create_run(assistant_set, specific_thread_id, run_instructions)
            if not specific_thread_id:
                assistant_set.run = run

            while run.status != "completed":
                run = openai.beta.threads.runs.retrieve(run_id= run.id, thread_id= specific_thread_id if specific_thread_id else assistant_set.thread.id)
                if run.completed_at:
                    # elapsed = ai.get_run_duration(run)
                    # print(f"run in: {elapsed}")
                    assistant_set.run = run
                    return ai.RunResult.SUCCESS
                
                time.sleep(1)
                
                if run.status != "completed" and ai.has_allowed_time_elapsed(assistant_set, start_time):
                    return ai.RunResult.TIMEOUT
                
        except Exception as ex:
            return ai.RunResult.ERROR
    
    async def run_all_threads_paralell_async(assistant_set, specific_thread_ids, run_instructions = None):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futureTasks = []
            # Add each task to ThreadPoolExecutor
            for specific_thread_id in specific_thread_ids:
                loop = asyncio.get_running_loop()
                future = loop.run_in_executor(executor, ai.run, assistant_set, specific_thread_id, run_instructions)
                futureTasks.append(future)

            # Await all run tasks to be finished
            return await asyncio.gather(*futureTasks)
            
        
    class RunResult(Enum):
        SUCCESS = 1
        #ONGOING = 0,
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
            return f"Runner has timeout. Took more than: {ai.max_allowed_run_seconds(assistant_set)}s. to proceed {ai.timeout_tag}"
            
    def get_last_answer(assistant_set):
        return ai.get_last_thread_answer(assistant_set.thread.id)
    
    def get_last_thread_answer(thread_id):
        try:
            messages = openai.beta.threads.messages.list(thread_id= thread_id)
            answer_role = "assistant"
            answers_data = [message for message in messages.data if message.role == answer_role ]
            if len(answers_data) == 0 or len(answers_data[0].content) == 0:
                return "~ pas de réponse ~"
            return answers_data[0].content[0].text.value
        
        except Exception as e:
            print(f"\nImpossible de trouver de message pour le thread: {thread_id}: {e}")
    
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
        return f"{response}"

    def get_all_messages_as_json(assistant_set):
        messages = openai.beta.threads.messages.list(assistant_set.thread.id)
        messages_json = []
        for data in messages.data:            
            for content in data.content:
                message = {
                    "source": data.role,
                    "content": content.text.value
                }
                messages_json.append(message)   
        return messages_json[::-1] #reverse messages' order
            
    def get_run_duration_seconds(run):
        return misc.get_elapsed_time_seconds(run.created_at, run.completed_at)
     
    def delete_assistant_set(assistant):
        openai.beta.assistants.delete(assistant_id= assistant.assistant.id)
        openai.beta.threads.delete(thread_id= assistant.thread.id)

    def print_openai_models():
        models = openai.models.list()
        for model in models:
            print(model.id)