import openai
import time
import uuid
from datetime import datetime, timedelta

from AssistModel import AssistantModel, AssistantIdsModel

class ai:    
    def create_full_assistant(model, instructions, message = None):
        assistant = ai.create_assistant(model, instructions)
        thread = ai.create_thread()
        if message:
            ai.add_message(thread.id, message)
        run = ai.create_run(assistant.id, thread.id)
        return AssistantModel(
            assistant= assistant,
            thread= thread,
            run= run
        )

    def create_assistant(model, instructions):
        return openai.beta.assistants.create(
            name= f"auto_assist_{str(uuid.uuid4())}",
            instructions= instructions,
            model=model
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

    def create_run(assistant_id, thread_id):
        return openai.beta.threads.runs.create(
            assistant_id= assistant_id,
            thread_id= thread_id,
            instructions= "be factual but write an accessible answer"
        )
    
    def wait_for_runner_completion(run_id, thread_id):
        sleep_interval = 2
        max_allowed_time = 40
        start_time = datetime.now()
        run_completed = False

        def has_allowed_time_elapsed():
            return start_time - datetime.now() > timedelta(seconds= max_allowed_time)

        while True:
            try:
                run = openai.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run_id
                )
                if run.completed_at:
                    run_completed = True
                    elapsed_time = run.completed_at - run.created_at
                    formatted_elapsed_time = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))
                    messages = openai.beta.threads.messages.list(thread_id= thread_id)
                    last_message = messages.data[0]
                    response = last_message.content[0].text.value
                    return f"Assistant response: {response}"
                
            except Exception as ex:
                return f"Error while waiting for the runner to respond: {ex.with_traceback}"
                break
            time.sleep(sleep_interval)
            
            if has_allowed_time_elapsed():
                return f"Runner has timeout. It takes more than: {max_allowed_time}s."