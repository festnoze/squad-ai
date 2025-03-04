
from form_workflow_graph import FormWorkflowGraph
from common_tools.helpers.env_helper import EnvHelper 
from agent_tools import FormTools   
from langchain.globals import set_verbose

async def main_async():
    #set_verbose(True)

    yaml_path = "config/user_and_training_info_form.yaml"
    conversation = "Je m'appelle John Smith et je suis un développeur Python."

    llms_infos = EnvHelper.get_llms_infos_from_env_config()
    FormTools.init(llms_infos)
    workflow_graph = FormWorkflowGraph()
    workflow = await workflow_graph.run_async(yaml_path, conversation)

def print_form_struct(form):
    print("\nDescription de la structure du formulaire :\n")
    print(form)
    print("---------------------------------------------------------------------\n")

if __name__ == "__main__":
    import asyncio
    print("\nServer starting!\n")
    asyncio.run(main_async())
   

