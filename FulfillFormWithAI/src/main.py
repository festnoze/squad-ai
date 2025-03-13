import asyncio  
from langchain.globals import set_verbose
#
from agents import AgentHIL
from graph_workflow_form import GraphWorkflowForm
from agent_tools import FormTools 
#
from common_tools.helpers.env_helper import EnvHelper 
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.file_helper import file

def get_init_env_and_graph(form_struct_file_path:str = None, conversation_file_path:str = None):
    set_verbose(True)
    llms_infos = EnvHelper.get_llms_infos_from_env_config()
    FormTools.init(llms_infos)

    conversation = None if not file.exists(conversation_file_path) else file.get_as_str(conversation_file_path)
    workflow_graph = GraphWorkflowForm(agent_state_initial_values = { "form_structure_file_path": form_struct_file_path, "chat_history": conversation })    
    
    return workflow_graph

async def main_async(workflow_graph: GraphWorkflowForm = None):  
    if not workflow_graph: workflow_graph = get_init_env_and_graph()      

    await workflow_graph.run_async()

def print_form_struct(form):
    txt.print("\nDescription de la structure du formulaire :\n")
    txt.print(form)
    txt.print("---------------------------------------------------------------------\n")

graph_class = get_init_env_and_graph(form_struct_file_path = "config/LID_form.yaml", conversation_file_path = 'inputs/conversation.txt')
graph = graph_class.graph

if __name__ == "__main__":
    txt.activate_print = True
    txt.print("\nServeur demarré !\n")
    asyncio.run(main_async(graph_class))
   

