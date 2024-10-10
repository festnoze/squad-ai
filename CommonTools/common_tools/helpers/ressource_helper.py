import importlib.resources

import yaml

from common_tools.helpers.txt_helper import txt

class Ressource:
    
    prompts_package_name = 'common_tools.prompts'
    rag_configs_package_name = 'common_tools.rag.configs'

    @staticmethod
    def get_language_detection_prompt(remove_comments=True) -> str:
        """Loads and returns the content of rag_language_detection_query.txt"""
        with importlib.resources.open_text(Ressource.prompts_package_name, 'rag_language_detection_query.txt') as file_reader:
            content = file_reader.read()
            if remove_comments:
                content = txt.remove_commented_lines(content)
            return content

    @staticmethod
    def get_prefiltering_translation_instructions_prompt(remove_comments=True) -> str:
        """Loads and returns the content of rag_prefiltering_ask_for_translation_instructions.txt"""
        with importlib.resources.open_text(Ressource.prompts_package_name, 'rag_prefiltering_ask_for_translation_instructions.txt') as file_reader:
            content = file_reader.read()
            if remove_comments:
                content = txt.remove_commented_lines(content)
            return content

    @staticmethod
    def get_query_code_additional_instructions_prompt(remove_comments=True) -> str:
        """Loads and returns the content of rag_query_code_additionnal_instructions.txt"""
        with importlib.resources.open_text(Ressource.prompts_package_name, 'rag_query_code_additionnal_instructions.txt') as file_reader:
            content = file_reader.read()
            if remove_comments:
                content = txt.remove_commented_lines(content)
            return content

    @staticmethod
    def get_rag_retriever_query_prompt(remove_comments=True) -> str:
        """Loads and returns the content of rag_retriever_query.txt"""
        with importlib.resources.open_text(Ressource.prompts_package_name, 'rag_retriever_query.txt') as file_reader:
            content = file_reader.read()
            if remove_comments:
                content = txt.remove_commented_lines(content)
            return content

    @staticmethod
    def get_rag_pipeline_default_config_1(remove_comments=True) -> str:
        """Loads and returns the content of rag_pipeline_default_config_1.yaml"""
        with importlib.resources.open_text(Ressource.rag_configs_package_name, 'rag_pipeline_default_config_1.yaml') as file_reader:
            content = file_reader.read()
            if remove_comments:
                content = txt.remove_commented_lines(content)
            return yaml.safe_load(content)
