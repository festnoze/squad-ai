import importlib.resources
import re
import yaml
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.file_helper import file

class Ressource:    
    prompts_package_name = 'common_tools.prompts'
    rag_configs_package_name = 'common_tools.rag.configs'

    @staticmethod
    def load_with_replaced_variables(file_name: str, variables_values: dict) -> str:
        ressource_content = Ressource.load_ressource_file(file_name)
        return Ressource.replace_variables(ressource_content, variables_values)
    
    @staticmethod
    def load_ressource_file(file_name: str, package_name: str = None, remove_comments=True) -> str:
        """The generic method to get the content of a file in prompts package"""
        if not package_name: 
            package_name = Ressource.prompts_package_name

        file_path = str(importlib.resources.files(package_name) / file_name)
        if package_name == Ressource.rag_configs_package_name:
            content = file.get_as_yaml(file_path)
        else:
            content = file.get_as_str(file_path, remove_comments=remove_comments)
        return content
        
    @staticmethod
    def replace_variables(prompt: str, variables: dict) -> str:
        prompt = prompt.replace('{{', '**(*(**').replace('}}', '**)*)**')  # Replace {{ and }} with **((** and **))** to avoid include them in the regex pattern
        pattern = re.compile(r'\{([^}]+)\}')
        def replacer(match):
            key = match.group(1)
            return variables.get(key, '')
        # Replace each {*} in variables' values first with the variables' values themselves or empty string
        for variable_key, variable_value in variables.items():
            variables[variable_key] = pattern.sub(replacer, variable_value)
        # Replace variables in the prompt
        result = pattern.sub(replacer, prompt)
        return result.replace('**(*(**', '{').replace('**)*)**', '}')  # Replace: '**((**' and '**))**' to '{' and '}'

    @staticmethod
    def remove_curly_brackets(text:str):
        return Ressource.replace_variables(text, {})

    @staticmethod
    def get_language_detection_prompt() -> str:
        return Ressource.load_ressource_file('rag_language_detection_query.txt')

    @staticmethod
    def get_query_rewritting_prompt() -> str:
        return Ressource.load_ressource_file('query_rewritting_prompt.txt')
        
    @staticmethod
    def get_create_standalone_query_from_history_prompt() -> str:
        return Ressource.load_ressource_file('create_standalone_query_from_history_prompt.txt')
        
    @staticmethod
    def get_prefiltering_translation_instructions_prompt() -> str:
        return Ressource.load_ressource_file('rag_prefiltering_ask_for_translation_instructions.txt')

    @staticmethod
    def get_query_code_additional_instructions_prompt() -> str:
        return Ressource.load_ressource_file('rag_query_code_additionnal_instructions.txt')
        
    @staticmethod
    def get_rag_augmented_generation_prompt_generic() -> str:
        return Ressource.load_ressource_file('rag_augmented_generation_query_generic.txt')

    @staticmethod
    def get_rag_augmented_generation_prompt_on_studi() -> str:
        return Ressource.load_ressource_file('rag_augmented_generation_query_on_studi.txt')

    @staticmethod
    def get_rag_augmented_generation_prompt_on_code() -> str:
        return Ressource.load_ressource_file('rag_augmented_generation_query_on_code.txt')
        
    @staticmethod
    def get_rag_pipeline_default_config_full_no_streaming() -> dict:
        content = Ressource.load_ressource_file('rag_pipeline_default_config_full_no_streaming.yaml', Ressource.rag_configs_package_name)
        return yaml.safe_load(content)
            
    @staticmethod
    def get_rag_pipeline_default_config_wo_AG_for_streaming() -> dict:
        content = Ressource.load_ressource_file('rag_pipeline_default_config_wo_AG_for_streaming.yaml', Ressource.rag_configs_package_name)
        return yaml.safe_load(content)
