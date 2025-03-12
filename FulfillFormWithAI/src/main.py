
from agents import AgentHIL
from graph_workflow_form import GraphWorkflowForm
from common_tools.helpers.env_helper import EnvHelper 
from agent_tools import FormTools   
from langchain.globals import set_verbose
import asyncio

def get_init_graph_and_env():
    #set_verbose(True)
    llms_infos = EnvHelper.get_llms_infos_from_env_config()
    FormTools.init(llms_infos)
    #
    workflow_graph = GraphWorkflowForm()    
    return workflow_graph

async def main_async(workflow_graph: GraphWorkflowForm = None):  
    if not workflow_graph: workflow_graph = get_init_graph_and_env()      
    yaml_path = "config/LID_form.yaml" #user_and_training_info_form.yaml"
    conversation = """
Je m'appelle John Smith, je suis un homme et je suis un développeur Python.
J'habote à Paris, au 16, rue de la biche escalier B. au 2ème étage 75016 en grande-bretagne et
je m'interesse à la formation "Bachelor developpeur Python" edans le domaine de l'IT.
Je suis joingnable de 8h à 17h au 0668686868 ou sur etie.mill@stud.com."""

    await workflow_graph.run_async(yaml_path, conversation)

def print_form_struct(form):
    print("\nDescription de la structure du formulaire :\n")
    print(form)
    print("---------------------------------------------------------------------\n")

graph_class = get_init_graph_and_env()
graph = graph_class.graph

if __name__ == "__main__":
    print("\nServeur demarré !\n")
    
    # Propose to auto-fill the form
    # input_auto_fill = 'm' # = input(">>> Tapez 'Entrée' pour procéder au remplissage automatique du formulaire, sinon tapez 'm' pour le remplir manuellement.\n")
    # if input_auto_fill != 'm':
    #     AgentHIL.static_answers = [
    #         "je m'appelle Etienne",
    #         "Monsieur",
    #         "Bouvier",
    #         "+33606060606",
    #         "erezr@efze.com",
    #         "622, avenue des roses 34000",
    #         "MONS",
    #         "domaine RH, bachelor conseiller en formation",
    #     ]            
    #     print(f"🤖 The questions will be automatically answered with the following static answers: \n{' / '.join(AgentHIL.static_answers)}.")
    #     print("\n>>> Début du remplissage automatique du formulaire <<<\n")

    asyncio.run(main_async(graph_class))
   

