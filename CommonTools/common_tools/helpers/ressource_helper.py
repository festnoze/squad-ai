import importlib.resources

import yaml

class Ressource:
    
    package_name = 'common_tools.prompts'

    @staticmethod
    def get_language_detection_prompt() -> str:
        """Loads and returns the content of rag_language_detection_query.txt"""
        with importlib.resources.open_text(Ressource.package_name, 'rag_language_detection_query.txt') as file_reader:
            return file_reader.read()

    @staticmethod
    def get_prefiltering_translation_instructions_prompt() -> str:
        """Loads and returns the content of rag_prefiltering_ask_for_translation_instructions.txt"""
        with importlib.resources.open_text(Ressource.package_name, 'rag_prefiltering_ask_for_translation_instructions.txt') as file_reader:
            return file_reader.read()

    @staticmethod
    def get_query_code_additional_instructions_prompt() -> str:
        """Loads and returns the content of rag_query_code_additionnal_instructions.txt"""
        with importlib.resources.open_text(Ressource.package_name, 'rag_query_code_additionnal_instructions.txt') as file_reader:
            return file_reader.read()

    @staticmethod
    def get_rag_retriever_query_prompt() -> str:
        """Loads and returns the content of rag_retriever_query.txt"""
        with importlib.resources.open_text(Ressource.package_name, 'rag_retriever_query.txt') as file_reader:
            return file_reader.read()
        
    @staticmethod
    def get_rag_pipeline_default_config_1() -> str:
        """Loads and returns the content of rag_retriever_query_with_filters.txt"""
        with importlib.resources.open_text(Ressource.package_name, 'rag_pipeline_default_config_1.yaml') as file_reader:
            return yaml.safe_load(file_reader)