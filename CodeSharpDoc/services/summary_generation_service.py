from typing import Callable
from langchain_core.language_models import BaseChatModel
from langsmith import traceable
#
from common_tools.helpers.json_helper import JsonHelper
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.helpers.file_helper import file
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.llm_helper import Llm
from common_tools.models.llm_info import LlmInfo
#
from models.params_doc import MethodParametersDocumentation, MethodParametersDocumentationPydantic
from helpers.c_sharp_helper import CSharpHelper, CSharpXMLDocumentation
from models.struct_summaries_infos import MethodSummaryInfo, StructSummariesInfos
from models.structure_desc import StructureDesc
from models.structure_type import StructureType
from services.code_analyser_client import code_analyser_client
from services.csharp_code_analyser_service import CSharpCodeStructureAnalyser
from services.summary_generation_prompts import SummaryGenerationPrompts

class SummaryGenerationService:    
    using_json_output_parsing = True

    #@traceable #trace llm invoke through LangSmith
    @staticmethod
    def generate_and_save_all_summaries_all_csharp_files_from_folder(code_file_path: str, files_batch_size: int, llm_batch_size: int, existing_structs_desc: list[StructureDesc], llms_infos: list[LlmInfo]):  
        llms = LangChainFactory.create_llms_from_infos(llms_infos)
        paths_and_codes = file.get_files_paths_and_contents(code_file_path, 'cs', 'C# code')
        SummaryGenerationService.remove_already_analysed_files(existing_structs_desc, paths_and_codes)
        paths_and_codes = SummaryGenerationService.remove_auto_generated_files(paths_and_codes)

        # Split code files 'paths_and_codes' into batchs of 'files-batch-size' items
        paths_and_codes_batchs = []
        for i in range(0, len(paths_and_codes), files_batch_size):
            batch = list(paths_and_codes.items())[i:i+files_batch_size]
            paths_and_codes_batchs.append(batch)
        
        txt.print(f"Summaries generation for {len(paths_and_codes)} code structures (in {len(paths_and_codes_batchs)} batches).")
        global_missing_methods_summaries = 0
        global_missing_structs_summaries = 0

        # Process each batch sequentially
        total_elapsed = 0
        for i, paths_and_codes_batch in enumerate(paths_and_codes_batchs):
            txt.print("\nBatch n°" + str(i+1) + " of " + str(len(paths_and_codes_batchs)) + ":")
            paths_and_codes_chunk = dict(paths_and_codes_batch)                
            if len(paths_and_codes_chunk) == 0: continue
            structs_to_process = code_analyser_client.parse_and_analyse_code_files(list(paths_and_codes_chunk.keys()), False)
            CSharpCodeStructureAnalyser.chunkify_code_of_classes_methods(structs_to_process) 

            elapsed = SummaryGenerationService.generate_all_summaries_for_all_structures(llms, structs_to_process, llm_batch_size, f"Files batch n°{i+1}/{len(paths_and_codes_batchs)} - ") 
            total_elapsed += elapsed

            structs_summaries_infos, missing_methods_summaries, missing_structs_summaries = SummaryGenerationService.create_struct_summaries_infos(structs_to_process, True)
            global_missing_methods_summaries += missing_methods_summaries
            global_missing_structs_summaries += missing_structs_summaries
            if missing_methods_summaries != 0: txt.print(f"Missing methods summaries: {missing_methods_summaries}")
            if missing_structs_summaries != 0: txt.print(f"Missing structs summaries: {missing_structs_summaries}")
            code_analyser_client.add_summaries_to_code_files(structs_summaries_infos)
            
        txt.print("\nAll summaries generated & codes files saved with new summaries.")
        txt.print(f"Total missing methods summaries: {global_missing_methods_summaries}")
        txt.print(f"Total missing structs summaries: {global_missing_structs_summaries}")
        txt.print(f"Total elapsed time: {total_elapsed}s.")
        txt.print("---------------------------")

    @staticmethod
    def generate_all_summaries_for_all_structures(llms: list[BaseChatModel], structures: list[StructureDesc], llm_batch_size: int, action_name_prefix: str)-> int:
        txt.print_with_spinner(f"Ongoing parallel summaries generation for {SummaryGenerationService.classes_methods_count(structures)} methods in {len(structures)} code files:")
        SummaryGenerationService.generate_all_summaries_for_all_classes(llms, llm_batch_size, structures, action_name_prefix)        
        SummaryGenerationService.apply_to_interfaces_the_classes_generated_summaries(structures)
        elapsed = txt.stop_spinner_replace_text(f"{SummaryGenerationService.classes_methods_count(structures)}  methods' summaries generation finished on {len(structures)} code files.")
        return elapsed
    
    @staticmethod
    def generate_all_summaries_for_all_classes(llms: list[BaseChatModel], llm_batch_size: int, known_structures: list[StructureDesc], action_name_prefix: str):
        all_classes_records_enums = [s for s in known_structures 
                               if s.struct_type == StructureType.Class 
                               or s.struct_type == StructureType.Record 
                               or s.struct_type == StructureType.Enum]
        
        SummaryGenerationService.generate_methods_summaries_all_classes(llms, llm_batch_size, all_classes_records_enums, action_name_prefix)
        
        SummaryGenerationService.generate_all_classes_methods_parameters_desc_w_output_parser(llms, llm_batch_size, all_classes_records_enums, action_name_prefix)
         
        SummaryGenerationService.generate_methods_return_summaries_all_classes(llms, all_classes_records_enums, action_name_prefix)

        # Generate the global summary for the structures themselves(classes, records, enums, but not for interfaces)        
        SummaryGenerationService.generate_structures_global_summaries(llms, all_classes_records_enums, action_name_prefix)

        # Assign to all methods a generated summary including method description, parameters description, and return type description
        for class_struct in all_classes_records_enums:
            for i in range(len(class_struct.methods)):
                method = class_struct.methods[i]
                xml_doc = CSharpXMLDocumentation(method.generated_summary, method.generated_parameters_summaries, method.generated_return_summary, None) #method.example
                method.generated_xml_summary = xml_doc.to_xml()

    @staticmethod
    def generate_methods_summaries_all_classes(llms: list[BaseChatModel], llm_batch_size: int, all_classes, action_name_prefix: str):
        action_name = action_name_prefix + "Generate methods description"
        prompts = SummaryGenerationPrompts.get_all_methods_prompts(all_classes, lambda method: True, SummaryGenerationPrompts.get_prompt_to_generate_method_summary)
        methods_summaries = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(action_name, llms, None, llm_batch_size, *prompts)
        SummaryGenerationService.apply_generated_summaries_to_classes_methods(all_classes, methods_summaries)

    @staticmethod
    def apply_generated_summaries_to_classes_methods(known_structures, methods_summaries):      
        count = SummaryGenerationService.classes_methods_count(known_structures)
        if count != len(methods_summaries):
            raise Exception(f"Error: they're {len(methods_summaries)} generated summaries, which doesn't match the count of {count} methods in classes of the current batch.")
        
        i = 0 
        for class_struct in known_structures:
            for method in class_struct.methods:
                method.generated_summary = methods_summaries[i]
                i += 1

    @staticmethod
    def generate_all_classes_methods_parameters_desc_w_output_parser(llms: list[BaseChatModel], llm_batch_size: int, classes: list[StructureDesc], action_name_prefix: str):      
        action_name = action_name_prefix + 'Generate parameters descriptions'
        
        # Create prompts for each method's parameters summary generation
        prompts_str = SummaryGenerationPrompts.get_all_methods_prompts(classes, lambda method: any(method.params), SummaryGenerationPrompts.get_prompt_to_generate_parameters_summaries)
        prompts_for_output_parser = []
        for method_prompt in prompts_str:
            prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(method_prompt, MethodParametersDocumentationPydantic, MethodParametersDocumentation)
            prompts_for_output_parser.append(prompt_for_output_parser)

        if len(prompts_for_output_parser) == 0: 
            return
        
        # Invoke LLM by batch to generate summaries for all methods' parameters
        methods_parameters_summaries = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(action_name, llms, output_parser, llm_batch_size, *prompts_for_output_parser)
        
        # Assign generated parameters summaries to each method desc
        current_method_index = 0
        for class_struct in classes:
            for method in class_struct.methods:
                if any(method.params):
                    if current_method_index >= len(methods_parameters_summaries):
                        raise Exception("Error: the number of generated parameters summaries don't match the number of methods with params in all classes.")
                    if type(methods_parameters_summaries[current_method_index]) is list:
                        methods_parameters_summaries[current_method_index] = {'params_list': methods_parameters_summaries[current_method_index]}
                    if methods_parameters_summaries[current_method_index]:
                        method.generated_parameters_summaries = MethodParametersDocumentation(**methods_parameters_summaries[current_method_index])
                    else:
                        method.generated_parameters_summaries = MethodParametersDocumentation(params_list=[])
                    current_method_index += 1
                else:
                    method.generated_parameters_summaries = MethodParametersDocumentation(params_list=[])

    @staticmethod
    def generate_all_classes_methods_parameters_desc_wo_output_parser(llms: list[BaseChatModel], llm_batch_size: int, classes: list[StructureDesc]):
        action_name = 'Generate parameters descriptions (direct LLM json output)'
        for class_struct in classes:
            prompts_or_chains = []
            for method in class_struct.methods:
                method_prompt, json_formatting_spec_prompt = SummaryGenerationPrompts.get_prompt_to_generate_parameters_summaries(method)
                prompt_or_chain = method_prompt + json_formatting_spec_prompt
                prompts_or_chains.append(prompt_or_chain)

            methods_parameters_summaries = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(action_name, llms, None, llm_batch_size, *prompts_or_chains)
            for method, method_params_summaries in zip(class_struct.methods, methods_parameters_summaries):
                method_params_summaries_str = Llm.get_content(method_params_summaries)
                method_params_summaries_str = Llm.extract_json_from_llm_response(method_params_summaries_str)
                method.generated_parameters_summaries = MethodParametersDocumentation.from_json(method_params_summaries_str)

    @staticmethod
    def generate_methods_return_summaries_all_classes(llms: list[BaseChatModel], all_classes, action_name_prefix: str):
        action_name = action_name_prefix + 'Generate methods return descriptions'
        methods_return_summary_prompts = SummaryGenerationPrompts.get_all_methods_prompts(all_classes, lambda method: method.has_return_type(), SummaryGenerationPrompts.get_prompt_to_generate_method_return_summary)
        methods_return_summaries = Llm.invoke_parallel_prompts(action_name, llms, *methods_return_summary_prompts)

        # Apply generated return method summary to methods with a return type
        index = 0
        for class_struct in all_classes:
            for method in [met for met in class_struct.methods if met.has_return_type()]:
                method.generated_return_summary = methods_return_summaries[index]
                index += 1

    @staticmethod
    def generate_structures_global_summaries(llms: list[BaseChatModel], all_classes_records_enums: list[StructureDesc], action_name_prefix: str):
        action_name = action_name_prefix + 'Generate structures global descriptions'
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
    def create_struct_summaries_infos(structure_descs: list[StructureDesc], from_generated_summary: bool) -> list[StructSummariesInfos]:
        struct_summaries_list : list[StructSummariesInfos] = []
        missing_methods_summaries = 0
        missing_structs_summaries = 0
        struct_summary_prop_name = 'generated_summary' if from_generated_summary else 'existing_summary'
        method_summary_prop_name = 'generated_xml_summary' if from_generated_summary else 'existing_summary'

        for struct_desc in structure_descs:
            method_summaries = []
            for method in struct_desc.methods:
                method_summary = ''
                if hasattr(method, method_summary_prop_name):
                    method_summary = getattr(method, method_summary_prop_name)
                    if not method_summary:
                        method_summary = ''
                        missing_methods_summaries += 1
                else:
                    method_summary = ''
                    missing_methods_summaries += 1

                method_summaries.append(MethodSummaryInfo(method.code_start_index, method_summary))
            
            struct_summary = ''
            if hasattr(struct_desc, struct_summary_prop_name):
                struct_summary = getattr(struct_desc, struct_summary_prop_name)
                if not struct_summary:
                    struct_summary = ''
                    missing_structs_summaries += 1
            else:
                struct_summary = ''
                missing_structs_summaries += 1

            struct_summary_info = StructSummariesInfos(
                file_path=struct_desc.file_path,
                index_shift_code=struct_desc.index_shift_code,
                indent_level=struct_desc.indent_level,
                summary=struct_summary,
                methods=method_summaries
            )
            struct_summaries_list.append(struct_summary_info)

        return struct_summaries_list, missing_methods_summaries, missing_structs_summaries
    
    @staticmethod
    def remove_already_analysed_files(existing_structs_desc, paths_and_codes):
        existing_structs_file_paths = [struct.file_path for struct in existing_structs_desc]
        removed_keys = [] 
        for path in paths_and_codes.keys():
            if path in existing_structs_file_paths:
                removed_keys.append(path)
        for key in removed_keys:
            del paths_and_codes[key]
    
    @staticmethod
    def remove_auto_generated_files(paths_and_codes):
        auto_generated_files_path_by_content = [path for path, code in paths_and_codes.items() if code and '<auto-generated>' in code]
        for path in auto_generated_files_path_by_content:
            del paths_and_codes[path]

        auto_generated_files_path_by_extension = [path for path in paths_and_codes.keys() if path.endswith(".g.cs") or path.endswith(".Designer.cs")]
        for path in auto_generated_files_path_by_extension:
            del paths_and_codes[path]

        return paths_and_codes

    @staticmethod
    def classes_methods_count(known_structures: list[StructureDesc]):
        count = 0
        for struct in known_structures:
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