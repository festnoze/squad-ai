import os
import time
from langchain_core.language_models import BaseChatModel
from helpers.display_helper import display
from langchains.langchain_factory import LangChainFactory
#
from helpers.file_helper import file
from helpers.txt_helper import txt
from helpers.c_sharp_helpers import CSharpXMLDocumentation
from helpers.llm_helper import Llm
from models.llm_info import LlmInfo
from models.method_desc import MethodDesc
from models.params_doc import MethodParametersDocumentation, MethodParametersDocumentationPydantic
from models.structure_desc import StructureDesc
from models.structure_types import StructureType
from services.csharp_code_analyser_service import CSharpCodeStructureAnalyser
import os

class SummaryGenerationService:
    @staticmethod
    def generate_summaries_for_csharp_files_and_save(file_path: str, llm_infos: LlmInfo):
       
        llm = SummaryGenerationService.get_llm(llm_infos)
        paths_and_codes = SummaryGenerationService.load_csharp_files(file_path)
        SummaryGenerationService.remove_existing_summaries_from_all_files(paths_and_codes)
        structures_descriptions = CSharpCodeStructureAnalyser.extract_code_structures_from_code_files(llm, paths_and_codes)
        SummaryGenerationService.generate_summaries_for_all_classes_methods(llm, structures_descriptions)
        paths_and_new_codes = SummaryGenerationService.including_generated_summaries_to_codes(paths_and_codes, structures_descriptions)
        file.save_contents_within_files(paths_and_new_codes)

        txt.print("\nDone.")
        txt.print("---------------------------")

    @staticmethod
    def get_llm(llm_infos):
        t = txt.print_with_spinner(f"Loading LLM model ...")
        llm = LangChainFactory.create_llm(
            adapter_type= llm_infos.type,
            llm_model_name= llm_infos.model,
            timeout_seconds= llm_infos.timeout,
            temperature= 1.0,
            api_key= llm_infos.api_key)
        txt.stop_spinner_replace_text("LLM model loaded successfully.")
        return llm

    
    @staticmethod
    def load_csharp_files(file_path):
        t = txt.print_with_spinner(f"Loading C# files ...")
        paths_and_codes = {}
        files = file.get_all_folder_and_subfolders_files(file_path, '.cs')
        for file_path in files:
            paths_and_codes[file_path] = file.get_as_str(file_path)
        txt.stop_spinner_replace_text(f"{len(paths_and_codes)} C# files loaded successfully.")
        return paths_and_codes
        
    @staticmethod
    def remove_existing_summaries_from_all_files(paths_and_codes):
        for file_path, code in paths_and_codes.items():
            lines = code.splitlines()
            lines = [line for line in lines if not line.strip().startswith('///')]
            paths_and_codes[file_path] = '\n'.join(lines)

    @staticmethod
    def generate_summaries_for_all_classes_methods(llm, known_structures):
        t = txt.print_with_spinner(f"Generate all summaries:")
        
        for class_struct in [s for s in known_structures if s.struct_type == StructureType.Class]:
            SummaryGenerationService.generate_methods_summaries_for_class(llm, class_struct, True)
        
        for interface_struct in [s for s in known_structures if s.struct_type == StructureType.Interface]:
            SummaryGenerationService.apply_interface_generated_summaries_of_classes(interface_struct, known_structures)

        txt.stop_spinner_replace_text("Summaries generated successfully.")

    @staticmethod
    def apply_interface_generated_summaries_of_classes(interface_structure: StructureDesc, known_structures: list[StructureDesc]):
            classes_implementing_interface = [s for s in known_structures if s.struct_type == StructureType.Class and interface_structure.struct_name in s.interfaces_names]
            interface_structure.related_structures = classes_implementing_interface #TODO: should add base classes too
            
            for method in interface_structure.methods:
                class_method = None
                for class_desc in classes_implementing_interface:
                    class_method = next((m for m in class_desc.methods if m.method_name == method.method_name), None)
                    if class_method:
                        break

                if class_method:
                    method.generated_summary = class_method.generated_summary
                    method.generated_parameters_summaries = class_method.generated_parameters_summaries
                    method.generated_return_summary = class_method.generated_return_summary
                    method.generated_xml_summary = class_method.generated_xml_summary

    @staticmethod
    def including_generated_summaries_to_codes(paths_and_codes, structures_descriptions):
        t = txt.print_with_spinner(f"Include summaries into the existing {len(paths_and_codes)} code files:")
        paths_and_codes_list = [(path, code) for path, code in paths_and_codes.items()]
        paths_and_new_codes = {}
        
        for structure_description, (file_path, code) in zip(structures_descriptions, paths_and_codes_list):
            if structure_description.file_path != file_path: raise Exception("Mismatch between lists")
            new_code = SummaryGenerationService.add_generated_summaries_to_initial_code(structure_description, code)
            paths_and_new_codes[file_path] = new_code

        txt.stop_spinner_replace_text("Summaries successfully included in initial files code.")
        return paths_and_new_codes

    @staticmethod
    def add_generated_summaries_to_initial_code(struct_desc: StructureDesc, initial_code: str):
        for method_desc in struct_desc.methods[::-1]:
            index = method_desc.code_start_index + struct_desc.index_shift_code

            if method_desc.has_attributs():
                index = initial_code[:index].rfind(method_desc.attributs[0])

            special_shift = 1# if struct_desc.structure_type == StructureType.Class.value else 2
            index = initial_code[:index].rfind('\n') + special_shift

            method_summary = '\n' + txt.indent(1, str(method_desc.generated_xml_summary))
            initial_code = initial_code[:index] + method_summary + initial_code[index:]
        return initial_code
        
    @staticmethod
    def generate_methods_summaries_for_class(llm: BaseChatModel, class_desc: StructureDesc, with_json_output_parsing: bool):
        if class_desc.struct_type != StructureType.Class:
            return
        
        # Generate all class' methods summaries
        methods_summaries_prompts = []
        for method in class_desc.methods:
            method_summary = SummaryGenerationService.generate_method_summary_prompt(llm, method)
            methods_summaries_prompts.append(method_summary)

        methods_summaries = Llm.invoke_parallel_prompts(llm, *methods_summaries_prompts)
        for method, method_summary in zip(class_desc.methods, methods_summaries):
            method.generated_summary = method_summary

        # Generate parameters description for all methods
        prompts_or_chains = []
        format_instructions = ''
        for method in class_desc.methods:
            prompt, json_formatting_spec_prompt = SummaryGenerationService.get_prompt_for_parameters_summaries(method, method_summary)        
            if with_json_output_parsing:
                prompt_or_chain, format_instructions = Llm.get_chain_for_json_output_parser(llm, prompt, MethodParametersDocumentationPydantic, MethodParametersDocumentation)
            else:
                prompt_or_chain = prompt + json_formatting_spec_prompt
            prompts_or_chains.append(prompt_or_chain)

        if with_json_output_parsing:
            methods_parameters_summaries = Llm.invoke_parallel_chains({Llm.output_parser_instructions_name: format_instructions}, *prompts_or_chains)
            for i in range(len(methods_parameters_summaries)):
                if type(methods_parameters_summaries[i]) is list:
                    methods_parameters_summaries[i] = {'params_list': methods_parameters_summaries[i]}
                methods_parameters_summaries[i] = MethodParametersDocumentation(**methods_parameters_summaries[i])
        else:
            methods_parameters_summaries = Llm.invoke_parallel_prompts(llm, *prompts_or_chains)

        if with_json_output_parsing:
            for method, method_params_summaries in zip(class_desc.methods, methods_parameters_summaries):
                method.generated_parameters_summaries = method_params_summaries
        else:            
            for method, method_params_summaries in zip(class_desc.methods, methods_parameters_summaries):
                method_params_summaries_str = Llm.get_llm_answer_content(method_params_summaries)
                method_params_summaries_str = Llm.extract_json_from_llm_response(method_params_summaries_str)
                method_params_summaries_built = MethodParametersDocumentation.from_json(method_params_summaries_str)
                method.generated_parameters_summaries = method_params_summaries_built

        # Generate method return summaries for all methods
        prompts = []
        for method in [met for met in class_desc.methods if met.has_return_type()]:
            prompts.append(SummaryGenerationService.get_prompt_for_method_return_summary(llm, method))
        methods_return_summaries_only = Llm.invoke_parallel_prompts(llm, *prompts)
        # Apply return method summary only to methods with a return type
        return_index = 0
        for i in range(len(class_desc.methods)):
            if class_desc.methods[i].has_return_type():
                class_desc.methods[i].generated_return_summary = methods_return_summaries_only[return_index]
                return_index += 1

        # Assign to all methods a generated summary including method description, parameters description, and return type description
        for i in range(len(class_desc.methods)):
            method = class_desc.methods[i]
            method.generated_xml_summary = str(CSharpXMLDocumentation(method.generated_summary, method.generated_parameters_summaries, method.generated_return_summary, None)) #method.example


    ctor_txt = "Take into account that this method is a constructor for the containing class of the same name."
    
    @staticmethod    
    def generate_method_summary_prompt(llm: BaseChatModel, method: MethodDesc) -> str:
        output_format = txt.single_line(f"""
                Respect the following format: Your answer must have a direct, conscise and factual style. 
                Your answer must always begin by an action verb, (like: 'Get', 'Retrieve', 'Update', 'Check', etc ...) to describe the aim of the method, 
                then possibly followed by any needed precisions, like: conditions, infos about concerned data, or anything else.
                For example: 'Retrieve the last message for a specified user' is a good formated answer, where as:
                'This method retrieves the last message by user ID' is not formated correctly.""")
        prompt = txt.single_line(f"""
                Analyse method name and the method code to produce a summary of it's functionnal purpose and behavior 
                without any mention to the method name or any technicalities, nor any mention whether it's asynchronous. 
                {SummaryGenerationService.ctor_txt if method.is_ctor else ""} {output_format}             
                The method name is: '{method.method_name}' and its full code is: """)
        
        prompt += Llm.embed_into_code_block('csharp', method.code)
        return prompt

        # TODO: see how to rather use code_chunks from method_desc for big methods
        # docs = Summarize.split_text(llm, text, max_tokens)
        # chain = Summarize.splitting_chain(llm)
        # method_summary = Summarize.split_prompt_and_invoke(llm, prompt, 8000)
        # return method_summary
    
    @staticmethod
    def get_prompt_for_parameters_summaries(method: MethodDesc, method_summary: str):      
        method_params_str = ', '.join([item.to_str() for item in method.params])

        # Base prompt w/o json output format spec. (used alone in case of further use of an output parser to convert the LLM response to the specified pydantic json object)
        method_params_summaries_prompt = txt.single_line(f"""\
            The list of parameters is: '{method_params_str}'. We have an existing method named: '{method.method_name}', 
            {SummaryGenerationService.ctor_txt if method.is_ctor else ""} for context, the method purpose is: '{method_summary}'.
            Generate a description for each parameter of the following C# method.""")
        
        # Prompt extension to specify the awaited json output format (used when no output parser is defined)
        json_formatting_spec_prompt = txt.single_line(f"""
            The awaited output should be a json array, with one item by parameter, each item having two keys: 
            - 'param_name': containing the parameter name, 
            - and 'param_desc': containing the description that you have generated of the parameter.""")
        
        return method_params_summaries_prompt, json_formatting_spec_prompt
     
    @staticmethod                   
    def get_prompt_for_method_return_summary(llm: BaseChatModel, method: MethodDesc) -> str:
        params_list = txt.get_prop_or_key(method.generated_parameters_summaries, 'params_list')
        params_list_str = ' ; '.join([str(item) for item in params_list])
        prompt = txt.single_line(f"""\
            Create a description of the return value of the following C# method.
            Instructions: You always begin with: 'Returns ' then generate a description of the return value. The description must be very short and synthetic (less than 15 words)
            The method name is: '{method.method_name}', {SummaryGenerationService.ctor_txt if method.is_ctor else ""} and to help you understand the purpose of the method, method summary is: '{method.generated_summary}'.
            The list of parameters is: '{params_list_str}'.""")
        return prompt
