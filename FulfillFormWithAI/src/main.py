async def main_async():
    # import time
    # from common_tools.helpers.import_helper import ImportHelper
    # from common_tools.helpers.txt_helper import txt
    # files_paths_to_test_for_import = [
    #     # "C:/Dev/IA/CommonTools/common_tools/rag/rag_service.py",
    #     # "C:/Dev/IA/CommonTools/common_tools/rag/rag_ingestion_pipeline/rag_ingestion_pipeline.py",
    #     # "C:/Dev/IA/CommonTools/common_tools/langchains/langchain_factory.py",
    #     # "src/form_service.py",
    #     # "src/llm_service.py",
    # ]
    # txt.activate_print = True
    # ImportHelper.test_api_imports_duration(files_paths_to_test_for_import)

    from agents_graph import LangGraphFormSupervisor
    from common_tools.helpers.env_helper import EnvHelper 
    from agent_tools import FormTools   
    from langchain.globals import set_verbose
    set_verbose(True)

    yaml_path = "config/user_and_training_info_form.yaml"
    conversation = "Je m'appelle John Smith et je suis un développeur Python."
    llms_infos = EnvHelper.get_llms_infos_from_env_config(skip_commented_lines=True)
    FormTools.init(llms_infos)
    supervisor = LangGraphFormSupervisor()
    workflow = await supervisor.run_async(yaml_path, conversation)

def print_form_struct(form):
    print("\nDescription de la structure du formulaire :\n")
    print(form)
    print("---------------------------------------------------------------------\n")

if __name__ == "__main__":
    import asyncio
    print("\nServer starting!\n")
    asyncio.run(main_async())
   

