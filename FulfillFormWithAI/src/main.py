
async def main_async():
    import time
    from common_tools.helpers.import_helper import ImportHelper
    from common_tools.helpers.txt_helper import txt

    # files_paths_to_test_for_import = [
    #     # "C:/Dev/IA/CommonTools/common_tools/rag/rag_service.py",
    #     # "C:/Dev/IA/CommonTools/common_tools/rag/rag_ingestion_pipeline/rag_ingestion_pipeline.py",
    #     # "C:/Dev/IA/CommonTools/common_tools/langchains/langchain_factory.py",
    #     # "src/form_service.py",
    #     # "src/llm_service.py",
    # ]
    # txt.activate_print = True
    # ImportHelper.test_api_imports_duration(files_paths_to_test_for_import)

    from form_service import FormService
    from llm_service import LlmService
    form_filename = 'user_and_training_info_form'
    form = FormService.create_form_from_yaml_file(f"config/{form_filename}.yaml")
    print("Loaded form:")
    print(form)
    
    llm_service = LlmService()
    out_dir = "outputs/"
    filled_form = await llm_service.query_user_to_fill_form_async(form)
    filled_form.save_form_instance_as_json(out_dir + "filled_form.json")
    filled_form.save_form_instance_as_flat_fields_json(out_dir + "filled_form_flat.json")

    print("Fulfilled form:")
    print(filled_form)


def print_form_struct(form):
    print("\nDescription de la structure du formulaire :\n")
    print(form)
    print("---------------------------------------------------------------------\n")

# if __name__ == "__main__":
#     import asyncio
#     print("\nServer starting!\n")
#     asyncio.run(main_async())

if __name__ == "__main__":
    from agents_graph import LangGraphFormSupervisor
    print("🔄 Construction du LangGraph pour le remplissage de formulaire...")
    supervisor = LangGraphFormSupervisor(None)
    workflow = supervisor.build_graph()
    print("✅ Graphe LangGraph compilé et exécution lancé !")
    workflow.run()

