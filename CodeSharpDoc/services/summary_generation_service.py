import os
import time
from langchain_core.language_models import BaseChatModel
from langchains.langchain_factory import LangChainFactory
from langsmith import traceable
#
from helpers.file_helper import file
from helpers.txt_helper import txt
from helpers.c_sharp_helper import CSharpHelper, CSharpXMLDocumentation
from helpers.llm_helper import Llm
from models.llm_info import LlmInfo
from models.method_desc import MethodDesc
from models.params_doc import MethodParametersDocumentation, MethodParametersDocumentationPydantic
from models.structure_desc import StructureDesc
from models.structure_types import StructureType
from services.csharp_code_analyser_service import CSharpCodeStructureAnalyser
import os

class SummaryGenerationService:    
    batch_size = 200
    using_json_output_parsing = True

    @traceable #trace llm invoke through LangSmith
    @staticmethod
    def generate_all_summaries_for_all_csharp_files_and_save(file_path: str, llms_infos: list[LlmInfo]):  
        txt.activate_print = True

        llms = LangChainFactory.create_llms_from_infos(llms_infos)       
         
        paths_and_codes = file.load_csharp_files(file_path)

        CSharpHelper.remove_existing_summaries_from_all_files(paths_and_codes)

        known_structures = CSharpCodeStructureAnalyser.extract_code_structures_from_code_files(llms, paths_and_codes)

        SummaryGenerationService.generate_methods_summaries_for_all_structures(llms, known_structures)
        
        paths_and_new_codes = SummaryGenerationService.including_generated_summaries_to_codes(paths_and_codes, known_structures)

        file.save_contents_within_files(paths_and_new_codes)
        
        txt.print("\nDone.")
        txt.print("---------------------------")
    
    @staticmethod
    def methods_count(known_structures: list[StructureDesc]):
        count = 0
        for struct in known_structures:
            if struct.struct_type == StructureType.Class:
                count += len(struct.methods)
        return count

    @staticmethod
    def apply_to_interfaces_the_classes_generated_summaries(known_structures: list[StructureDesc]):
        for interface_structure in [s for s in known_structures if s.struct_type == StructureType.Interface]:
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
        txt.print_with_spinner(f"Include summaries into the existing {len(paths_and_codes)} code files:")
        paths_and_codes_list = [(path, code) for path, code in paths_and_codes.items()]
        paths_and_new_codes = {}
        
        for structure_description in structures_descriptions:
            code = paths_and_codes[structure_description.file_path]
            new_code = SummaryGenerationService.add_generated_summaries_to_initial_code(structure_description, code)
            paths_and_new_codes[structure_description.file_path] = new_code
        
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

            method_summary = '\n' + txt.indent(1, method_desc.generated_xml_summary)
            initial_code = initial_code[:index] + method_summary + initial_code[index:]
        return initial_code

    @staticmethod
    def get_classes_flatten_prompts(all_classes: list[StructureDesc], classes_methods_summaries_prompts: dict):
        flatten_prompts = []
        for class_struct in all_classes:
            for prompt in classes_methods_summaries_prompts[class_struct.struct_name]:
                flatten_prompts.append(prompt)
        return flatten_prompts

    @staticmethod
    def generate_methods_summaries_for_all_structures(llms: list[BaseChatModel], known_structures: list[StructureDesc]):
        txt.print_with_spinner(f"Ongoing parallel summaries generation for {SummaryGenerationService.methods_count(known_structures)} methods in {len(known_structures)} code files:")
        SummaryGenerationService.generate_methods_summaries_for_all_classes(llms, known_structures)        
        SummaryGenerationService.apply_to_interfaces_the_classes_generated_summaries(known_structures)
        txt.stop_spinner_replace_text("All methods' summaries generated successfully")

    @staticmethod
    def generate_methods_summaries_for_all_classes(llm: BaseChatModel, known_structures: list[StructureDesc]):
        all_classes = [s for s in known_structures if s.struct_type == StructureType.Class]
        
        SummaryGenerationService.generate_methods_summaries_only_all_classes(llm, known_structures, all_classes)
        
        if SummaryGenerationService.using_json_output_parsing:
            SummaryGenerationService.generate_all_classes_methods_parameters_desc_json_from_output_parser(llm, all_classes)
        else:
            SummaryGenerationService.generate_all_classes_methods_parameters_desc_json_from_llm(llm, all_classes)
            
        SummaryGenerationService.generate_methods_return_summaries_for_all_classes(llm, all_classes)

        #TODO: Generate a summary for the structures (classes, interfaces, etc) themselves

        # Assign to all methods a generated summary including method description, parameters description, and return type description
        for class_struct in all_classes:
            for i in range(len(class_struct.methods)):
                method = class_struct.methods[i]
                xml_doc = CSharpXMLDocumentation(method.generated_summary, method.generated_parameters_summaries, method.generated_return_summary, None) #method.example
                method.generated_xml_summary = xml_doc.to_xml()

    @staticmethod
    def generate_methods_summaries_only_all_classes(llms: list[BaseChatModel], known_structures, all_classes):
        action_name = "Generate methods description"
        methods_summaries_prompts_by_classes =  SummaryGenerationService.generate_methods_summary_prompts_by_class(all_classes)
        prompts = SummaryGenerationService.get_classes_flatten_prompts(all_classes, methods_summaries_prompts_by_classes)
        methods_summaries = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(action_name, llms, None, SummaryGenerationService.batch_size, *prompts)
        SummaryGenerationService.apply_generated_summaries_to_classes_methods(known_structures, methods_summaries_prompts_by_classes, methods_summaries)

    @staticmethod
    def generate_all_classes_methods_parameters_desc_json_from_output_parser(llms: list[BaseChatModel], all_classes):
        action_name = 'Generate parameters descriptions (output parser)'
        for class_struct in all_classes:
            prompts = []
            format_instructions = ''
            for method in class_struct.methods:
                method_prompt, json_formatting_prompt = SummaryGenerationService.get_prompt_for_parameters_summaries(method)
                prompt, output_parser = Llm.get_prompt_and_json_output_parser(method_prompt, MethodParametersDocumentationPydantic, MethodParametersDocumentation)
                prompts.append(prompt)

            methods_parameters_summaries = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(action_name, llms, output_parser, SummaryGenerationService.batch_size, *prompts)

            for i in range(len(methods_parameters_summaries)):
                if type(methods_parameters_summaries[i]) is list:
                    methods_parameters_summaries[i] = {'params_list': methods_parameters_summaries[i]}
                if methods_parameters_summaries[i]:
                    methods_parameters_summaries[i] = MethodParametersDocumentation(**methods_parameters_summaries[i])
                else:
                    methods_parameters_summaries[i] = MethodParametersDocumentation(params_list=[])

            for method, method_params_summaries in zip(class_struct.methods, methods_parameters_summaries):
                method.generated_parameters_summaries = method_params_summaries

    @staticmethod
    def generate_all_classes_methods_parameters_desc_json_from_llm(llms: list[BaseChatModel], all_classes):
        action_name = 'Generate parameters descriptions (direct LLM json output)'
        for class_struct in all_classes:
            prompts_or_chains = []
            for method in class_struct.methods:
                method_prompt, json_formatting_spec_prompt = SummaryGenerationService.get_prompt_for_parameters_summaries(method)
                prompt_or_chain = method_prompt + json_formatting_spec_prompt
                prompts_or_chains.append(prompt_or_chain)

            methods_parameters_summaries = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(action_name, llms, None, SummaryGenerationService.batch_size, *prompts_or_chains)
            for method, method_params_summaries in zip(class_struct.methods, methods_parameters_summaries):
                method_params_summaries_str = Llm.get_llm_answer_content(method_params_summaries)
                method_params_summaries_str = Llm.extract_json_from_llm_response(method_params_summaries_str)
                method.generated_parameters_summaries = MethodParametersDocumentation.from_json(method_params_summaries_str)

    @staticmethod
    def generate_methods_return_summaries_for_all_classes(llms: list[BaseChatModel], all_classes):
        action_name = 'Generate methods return descriptions'
        for class_struct in all_classes:
            class_prompts = []
            for method in [met for met in class_struct.methods if met.has_return_type()]:
                class_prompts.append(SummaryGenerationService.get_prompt_for_method_return_summary(method))
            methods_return_summaries_only = Llm.invoke_parallel_prompts(action_name, llms, *class_prompts)
            
            # Apply return method summary only to methods with a return type
            return_index = 0
            for i in range(len(class_struct.methods)):
                if class_struct.methods[i].has_return_type():
                    class_struct.methods[i].generated_return_summary = methods_return_summaries_only[return_index]
                    return_index += 1

    @staticmethod
    def generate_methods_summary_prompts_by_class(all_classes: list[StructureDesc]):
        classes_methods_summaries_prompts = {}
        for class_struct in all_classes: 
            class_methods_summaries_prompts = []
            for method in class_struct.methods:
                method_summary = SummaryGenerationService.generate_method_summary_prompt(method)
                class_methods_summaries_prompts.append(method_summary)
            classes_methods_summaries_prompts[class_struct.struct_name] = class_methods_summaries_prompts
        return classes_methods_summaries_prompts
    
    @staticmethod
    def apply_generated_summaries_to_classes_methods(known_structures, classes_methods_summaries_prompts: dict, methods_summaries):
        i = 0
        for class_name in classes_methods_summaries_prompts.keys():
            class_struct = next((s for s in known_structures if s.struct_name == class_name), None)
            if class_struct is None: raise Exception(f"Class {class_name} not found in loaded files")

            for method in class_struct.methods:
                method.generated_summary = methods_summaries[i]
                i += 1


    ctor_txt = "Take into account that this method is a constructor for the containing class of the same name."
    
    @staticmethod    
    def generate_method_summary_prompt(method: MethodDesc) -> str:
        output_format = txt.single_line(f"""
                Respect the following format: Your answer must have a direct, conscise and factual style. 
                Your answer must always begin by an action verb, (like: 'Get', 'Retrieve', 'Update', 'Check', etc ...) to describe the aim of the method, 
                then possibly followed by any needed precisions, like: conditions, infos about concerned data, or anything else.
                For example: 'Retrieve the last message for a specified user' is a good formated answer, where as:
                'This method retrieves the last message by user ID' is not formated correctly.""")
        prompt = txt.single_line(f"""
                Analyse method name and the method code to produce a single sentence summary of it's functionnal purpose and behavior 
                without any mention to the method name or any technicalities, nor any mention whether it's asynchronous, nor to its parameter, unless itmake sense to explain the method purpose. 
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
    def get_prompt_for_parameters_summaries(method: MethodDesc):      
        method_params_str = ', '.join([item.to_str() for item in method.params])

        # Base prompt w/o json output format spec. (used alone in case of further use of an output parser to convert the LLM response to the specified pydantic json object)
        method_params_summaries_prompt = txt.single_line(f"""\
            The list of parameters is: '{method_params_str}'. We have an existing method named: '{method.method_name}', 
            {SummaryGenerationService.ctor_txt if method.is_ctor else ""} for context, the method purpose is: '{method.generated_summary}'.
            Generate a description for each parameter of the following C# method.""")
        
        # Prompt extension to specify the awaited json output format (used when no output parser is defined)
        json_formatting_spec_prompt = txt.single_line(f"""
            The awaited output should be a json array, with one item by parameter, each item having two keys: 
            - 'param_name': containing the parameter name, 
            - and 'param_desc': containing the description that you have generated of the parameter.""")
        
        return method_params_summaries_prompt, json_formatting_spec_prompt
     
    @staticmethod                   
    def get_prompt_for_method_return_summary(method: MethodDesc) -> str:
        params_list = txt.get_prop_or_key(method.generated_parameters_summaries, 'params_list')
        params_list_str = ' ; '.join([str(item) for item in params_list])
        prompt = txt.single_line(f"""\
            Create a description of the return value of the following C# method.
            Instructions: You always begin with: 'Returns ' then generate a description of the return value. The description must be very short and synthetic (less than 15 words)
            The method name is: '{method.method_name}', {SummaryGenerationService.ctor_txt if method.is_ctor else ""} and to help you understand the purpose of the method, method summary is: '{method.generated_summary}'.
            The list of parameters is: '{params_list_str}'.""")
        return prompt
