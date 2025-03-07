
from graph_workflow_form import GraphWorkflowForm
from common_tools.helpers.env_helper import EnvHelper 
from agent_tools import FormTools   
from langchain.globals import set_verbose
import asyncio

def init_graph():
    #set_verbose(True)
    llms_infos = EnvHelper.get_llms_infos_from_env_config()
    FormTools.init(llms_infos)
    workflow_graph = GraphWorkflowForm()
    return workflow_graph

async def main_async(workflow_graph: GraphWorkflowForm = None):        
    yaml_path = "config/user_and_training_info_form.yaml"
    conversation = "Je m'appelle John Smith et je suis un développeur Python. J'habote à Paris, au 16, rue de la biche 75016 en Angleterre."
    
    if not workflow_graph: workflow_graph = init_graph()
    await workflow_graph.run_async(yaml_path, conversation)

def print_form_struct(form):
    print("\nDescription de la structure du formulaire :\n")
    print(form)
    print("---------------------------------------------------------------------\n")

graph = init_graph()

if __name__ == "__main__":
    print("\nServer starting!\n")
    asyncio.run(main_async(graph))
   

