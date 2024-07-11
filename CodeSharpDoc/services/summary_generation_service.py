import os
import time
from langchain_core.language_models import BaseChatModel
from helpers.json_helper import JsonHelper
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
from models.struct_summaries_infos import MethodSummaryInfo, StructSummariesInfos
from models.structure_desc import StructureDesc
from models.structure_types import StructureType
from services.code_analyser_client import code_analyser_client
from services.csharp_code_analyser_service import CSharpCodeStructureAnalyser
import os
import json

from services.summary_generation_prompts import SummaryGenerationPrompts

class SummaryGenerationService:    
    batch_size = 200
    using_json_output_parsing = True

    #@traceable #trace llm invoke through LangSmith
    @staticmethod
    def generate_and_save_all_summaries_all_csharp_files_from_folder(file_path: str, existing_structs_desc: list[StructureDesc], llms_infos: list[LlmInfo]):  
        txt.activate_print = True
        llms = LangChainFactory.create_llms_from_infos(llms_infos)
        paths_and_codes = file.get_files_paths_and_contents(file_path, 'cs')

        SummaryGenerationService.remove_already_analysed_files(existing_structs_desc, paths_and_codes)
        if len(paths_and_codes) == 0: return

        #structures_from_python = CSharpCodeStructureAnalyser.extract_code_structures_from_code_files(paths_and_codes)
        structs_to_process = code_analyser_client.parse_and_analyse_code_files(list(paths_and_codes.keys()))
        
        #SummaryGenerationService.copy_missing_infos(structures_from_python, known_structures)
        CSharpCodeStructureAnalyser.chunkify_code_of_classes_methods(structs_to_process) 

        SummaryGenerationService.generate_methods_summaries_for_all_structures(llms, structs_to_process) 

        structs_summaries_infos = SummaryGenerationService.create_struct_summaries_infos(structs_to_process)

        # paths_and_new_codes = SummaryGenerationService.add_generated_summaries_to_initial_codes(paths_and_codes, structs_to_process)
        # file.save_contents_within_files(paths_and_new_codes)      
        # 2 above lines are replaced by this # call:
        code_analyser_client.add_summaries_to_code_files(structs_summaries_infos)
        
        JsonHelper.save_as_json_files(structs_to_process, 'outputs\\structures_descriptions')
        
        txt.print("\nDone.")
        txt.print("---------------------------")

    @staticmethod
    def create_struct_summaries_infos(structure_descs: list[StructureDesc]) -> list[StructSummariesInfos]:
        struct_summaries_list : list[StructSummariesInfos] = []
        for struct_desc in structure_descs:
            method_summaries = [
                MethodSummaryInfo(method.code_start_index, method.generated_xml_summary)
                for method in struct_desc.methods
            ]

            struct_summary_info = StructSummariesInfos(
                file_path=struct_desc.file_path,
                index_shift_code=struct_desc.index_shift_code,
                indent_level=struct_desc.indent_level,
                generated_summary=struct_desc.generated_summary,
                methods=method_summaries
            )

            struct_summaries_list.append(struct_summary_info)

        return struct_summaries_list

    @staticmethod
    def remove_already_analysed_files(existing_structs_desc, paths_and_codes):
        existing_structs_file_paths = [struct.file_path for struct in existing_structs_desc]
        removed_keys = [] 
        for path in paths_and_codes.keys():
            if path in existing_structs_file_paths:
                removed_keys.append(path)
        for key in removed_keys:
            del paths_and_codes[key]

    def load_struct_desc_from_folder(folder_path: str):
        json_files = file.get_files_paths_and_contents(folder_path, 'json')
        structures_descriptions = []
        for file_path in json_files:
            json_struct_desc = json.loads(json_files[file_path])
            structures_descriptions.append(StructureDesc(**json_struct_desc))
        return structures_descriptions

    @staticmethod
    def copy_missing_infos(structures_from_python, known_structures):        
        """ Copy all methods' params and code_start_index from python structures to csharp structures methods """
        for struct in known_structures:
            for method in struct.methods:
                for python_struct in structures_from_python:
                    if python_struct.struct_name == struct.struct_name:
                        for python_method in python_struct.methods:
                            if python_method.method_name == method.method_name:
                                method.code_start_index = python_method.code_start_index
                                break
    
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

    #obsolete
    @staticmethod
    def add_generated_summaries_to_initial_codes(paths_and_codes: dict, structures_summaries_infos: list):
        paths_and_new_codes = {}

        for file_path, code in paths_and_codes.items():
            # Determine all the concerned structures_summaries_infos for the current file
            relevant_structures = [s for s in structures_summaries_infos if s.file_path == file_path]

            if not relevant_structures:
                continue
            
            new_code = code

            for struct_info in sorted(relevant_structures, key=lambda m: m.index_shift_code, reverse=True):
                # Add methods summaries to the code
                for method in sorted(struct_info.methods, key=lambda m: m.code_start_index, reverse=True):
                    method_summary = method.generated_xml_summary.rstrip()
                    method_summary = '\n' + txt.indent(struct_info.indent_level + 1, method_summary)
                    before = new_code[:method.code_start_index]
                    after = new_code[method.code_start_index:]
                    new_code = before + method_summary + after

                # Add global structure summary to the code
                if struct_info.generated_summary:
                    global_summary = '\n' + txt.indent(struct_info.indent_level, struct_info.generated_summary.rstrip())
                    before = new_code[:struct_info.index_shift_code]
                    after = new_code[struct_info.index_shift_code:]
                    new_code = before + global_summary + after
            
            paths_and_new_codes[file_path] = new_code
        return paths_and_new_codes

    #obsolete
    @staticmethod
    def include_generated_summaries_to_codes(paths_and_codes, structures_descriptions):
        paths_and_new_codes = {}        
        txt.print_with_spinner(f"Include summaries into the existing {len(paths_and_codes)} code files:")

        for structure_description in structures_descriptions:
            code = paths_and_codes[structure_description.file_path]
            new_code = SummaryGenerationService.add_generated_summaries_to_initial_code(structure_description, code)
            paths_and_new_codes[structure_description.file_path] = new_code
        
        txt.stop_spinner_replace_text("Summaries successfully included in initial files code.")
        return paths_and_new_codes

    #obsolete
    @staticmethod
    def add_generated_summaries_to_initial_code(struct_desc: StructureDesc, code: str):
        # Add methods summaries to the code
        for method_desc in struct_desc.methods[::-1]:
            if method_desc.generated_xml_summary is None: 
                continue
            index = method_desc.code_start_index
            if index == -1: continue

            # if method_desc.attributes and len(method_desc.attributes) > 0: # has attributes
            #     index = initial_code[:index].rfind(method_desc.attributes[0])

            # special_shift = 1
            # index = initial_code[:index].rfind('\n') + special_shift

            method_summary = '\n' + txt.indent(method_desc.indent_level, method_desc.generated_xml_summary)
            #print(code[index:index+100])
            code = code[:index] + method_summary + code[index:]

        # Add global structure summay to the code
        if struct_desc.generated_summary is not None:
            global_summary = '\n' + txt.indent(struct_desc.indent_level, struct_desc.generated_summary)
            code = code[:struct_desc.index_shift_code] + global_summary + code[struct_desc.index_shift_code:]
        
        return code

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
        all_classes_records_enums = [s for s in known_structures 
                               if s.struct_type == StructureType.Class 
                               or s.struct_type == StructureType.Record 
                               or s.struct_type == StructureType.Enum]
        
        SummaryGenerationService.generate_methods_summaries_only_all_classes(llm, known_structures, all_classes_records_enums)
        
        if SummaryGenerationService.using_json_output_parsing:
            SummaryGenerationService.generate_all_classes_methods_parameters_desc_json_from_output_parser(llm, all_classes_records_enums)
        else:
            SummaryGenerationService.generate_all_classes_methods_parameters_desc_json_from_llm(llm, all_classes_records_enums)
            
        SummaryGenerationService.generate_methods_return_summaries_for_all_classes(llm, all_classes_records_enums)

        # Generate the global summary for the structures themselves(classes, records, enums, but not for interfaces)        
        SummaryGenerationService.generate_structures_global_summaries(llm, all_classes_records_enums)

        # Assign to all methods a generated summary including method description, parameters description, and return type description
        for class_struct in all_classes_records_enums:
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
    def apply_generated_summaries_to_classes_methods(known_structures, classes_methods_summaries_prompts: dict, methods_summaries):
        i = 0
        for class_name in classes_methods_summaries_prompts.keys():
            class_struct = next((s for s in known_structures if s.struct_name == class_name), None)
            if class_struct is None: raise Exception(f"Class {class_name} not found in loaded files")

            for method in class_struct.methods:
                method.generated_summary = methods_summaries[i]
                i += 1

    @staticmethod
    def generate_all_classes_methods_parameters_desc_json_from_output_parser(llms: list[BaseChatModel], all_classes: list[StructureDesc]):
        
        # Create prompts for each method's parameters summary generation
        prompts = []
        for class_struct in all_classes:
            if len(class_struct.methods) > 0:
                for method in class_struct.methods:
                    method_prompt, json_formatting_prompt = SummaryGenerationPrompts.get_prompt_to_generate_parameters_summaries(method)
                    prompt, output_parser = Llm.get_prompt_and_json_output_parser(method_prompt, MethodParametersDocumentationPydantic, MethodParametersDocumentation)
                    prompts.append(prompt)

        # Invoke LLM by batch to generate summaries for all methods' parameters
        action_name = 'Generate parameters descriptions (output parser)'
        if len(prompts) == 0: return
        
        methods_parameters_summaries = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(action_name, llms, output_parser, SummaryGenerationService.batch_size, *prompts)
        
        # Assign generated parameters summaries to each method desc
        current_method_index = 0
        for class_struct in all_classes:
            for method in class_struct.methods:
                if type(methods_parameters_summaries[current_method_index]) is list:
                    methods_parameters_summaries[current_method_index] = {'params_list': methods_parameters_summaries[current_method_index]}
                if methods_parameters_summaries[current_method_index]:
                    method.generated_parameters_summaries = MethodParametersDocumentation(**methods_parameters_summaries[current_method_index])
                else:
                    method.generated_parameters_summaries = MethodParametersDocumentation(params_list=[])
                current_method_index += 1

        if current_method_index != len(methods_parameters_summaries):
            raise Exception("Error: the number of generated parameters summaries don't match the number of methods in classes.")

    @staticmethod
    def generate_all_classes_methods_parameters_desc_json_from_llm(llms: list[BaseChatModel], all_classes):
        action_name = 'Generate parameters descriptions (direct LLM json output)'
        for class_struct in all_classes:
            prompts_or_chains = []
            for method in class_struct.methods:
                method_prompt, json_formatting_spec_prompt = SummaryGenerationPrompts.get_prompt_to_generate_parameters_summaries(method)
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
                class_prompts.append(SummaryGenerationPrompts.get_prompt_to_generate_method_return_summary(method))
            methods_return_summaries_only = Llm.invoke_parallel_prompts(action_name, llms, *class_prompts)
            
            # Apply return method summary only to methods with a return type
            return_index = 0
            for i in range(len(class_struct.methods)):
                if class_struct.methods[i].has_return_type():
                    class_struct.methods[i].generated_return_summary = methods_return_summaries_only[return_index]
                    return_index += 1

    @staticmethod
    def generate_structures_global_summaries(llms: list[BaseChatModel], all_classes_records_enums: list[StructureDesc]):
        action_name = 'Generate structures global descriptions'
        class_prompts = []
        for struct in all_classes_records_enums:
            if struct.struct_type == StructureType.Class or struct.struct_type == StructureType.Record:
                class_prompts.append(SummaryGenerationPrompts.get_prompt_to_generate_class_summary(struct))
            elif struct.struct_type == StructureType.Enum:
                class_prompts.append(SummaryGenerationPrompts.get_prompt_to_generate_enum_summary(struct))
            else:
                raise Exception(f"Error: unhandled structure type {struct.struct_type}")
            
        classes_summaries = Llm.invoke_parallel_prompts(action_name, llms, *class_prompts)
            
        # Apply classes generated summaries to all classes
        for i in range(len(all_classes_records_enums)):
            all_classes_records_enums[i].generated_summary = CSharpXMLDocumentation(classes_summaries[i]).to_xml()

    @staticmethod
    def generate_methods_summary_prompts_by_class(all_classes: list[StructureDesc]):
        classes_methods_summaries_prompts = {}
        for class_struct in all_classes: 
            class_methods_summaries_prompts = []
            for method in class_struct.methods:
                method_summary = SummaryGenerationPrompts.get_prompt_to_generate_method_summary(method)
                class_methods_summaries_prompts.append(method_summary)
            classes_methods_summaries_prompts[class_struct.struct_name] = class_methods_summaries_prompts
        return classes_methods_summaries_prompts