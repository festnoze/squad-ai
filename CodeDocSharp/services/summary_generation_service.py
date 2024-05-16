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
from services.csharp_code_analyser_service import CSharpCodeStructureAnalyser
import os

class SummaryGenerationService:
    @staticmethod
    def generate_summaries_for_csharp_files_and_save(file_path: str, llm_infos: LlmInfo):
        t = txt.print_with_spinner(f"Loading LLM model ...")
        llm = LangChainFactory.create_llm(
            adapter_type= llm_infos.type,
            llm_model_name= llm_infos.model,
            timeout_seconds= llm_infos.timeout,
            temperature= 1.0,
            api_key= llm_infos.api_key)
        txt.stop_spinner(t, "LLM model loaded successfully.")

        # Load C# file code
        t = txt.print_with_spinner(f"Loading C# files ...")
        files, dirs = file.get_folder_all_files_and_subfolders(file_path)
        for file_path in files:
            if file_path.endswith('.cs'):
                code = file.get_as_str(file_path)
                txt.stop_spinner(t, "Files loaded successfully.")

            # Remove existing summaries from code
            lines = code.splitlines()
            lines = [line for line in lines if not line.strip().startswith('///')]
            code = '\n'.join(lines)

            # Extract code structure from C# file
            t = txt.print_with_spinner(f"Parsing code structure:")
            class_description: StructureDesc = CSharpCodeStructureAnalyser.get_code_structure(llm, file_path, code)
            txt.stop_spinner(t, "Files code parsed successfully.")

            # Generate summaries for all methods for the current class
            t = txt.print_with_spinner(f"Generate all summaries:")
            SummaryGenerationService.generate_all_methods_summaries(llm, class_description, True)
            txt.stop_spinner(t, "Summaries generated successfully.")

            # Including generated summaries to class code
            t = txt.print_with_spinner(f"Include summaries into existing code:")
            new_code = SummaryGenerationService.generate_code_with_generated_summaries_from_initial_code(class_description, code)
            txt.stop_spinner(t, "Summaries successfully included in initial code.")

            # Save file with modified code
            t = txt.print_with_spinner(f"Saving files:")
            new_file_path = file_path.replace('.cs', '_modif.cs')
            file.write_file(new_code, new_file_path)
            txt.stop_spinner(t, "Files overrided and saved successfully.")
            txt.print("\nDone.")
            txt.print("---------------------------")

    @staticmethod
    def generate_code_with_generated_summaries_from_initial_code(class_description, initial_code: str):
        for method_desc in class_description.methods[::-1]:
            index = method_desc.code_start_index + class_description.index_shift_code
            next_nl_dist = initial_code[index:].find('\n')     

            if next_nl_dist != -1:
                next_nl_nindex = index + 2 # add +2 to include the newline+
            else:
                next_nl_nindex = len(initial_code)

            if method_desc.has_attributs():
                att_index = initial_code[:next_nl_nindex].rfind(method_desc.attributs[0])
                att_nl_index = initial_code[:att_index].rfind('\n')
                split_index = att_nl_index + 1 # add +1 to include the newline
            else:
                split_index = next_nl_nindex

            method_summary = '\n' + txt.indent(1, str(method_desc.generated_xml_summary))
            initial_code = initial_code[:split_index] + method_summary + initial_code[split_index:]
        return initial_code
        
    @staticmethod
    def generate_all_methods_summaries(llm: BaseChatModel, class_desc: StructureDesc, with_json_output_parsing: bool):
        # Generate methods summaries
        methods_summaries_prompts = []
        for method in class_desc.methods:
            method_summary = SummaryGenerationService.generate_method_summary_prompt(llm, method)
            methods_summaries_prompts.append(method_summary)

        methods_summaries = Llm.invoke_parallel_prompts(llm, *methods_summaries_prompts)
        for method, method_summary in zip(class_desc.methods, methods_summaries):
            method.generated_summary = method_summary

        # Generate parameters summaries for all methods
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
            method.generated_xml_summary = CSharpXMLDocumentation(method.generated_summary, method.generated_parameters_summaries, method.generated_return_summary, None) #method.example


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
        prompt += '\n```csharp' + method.code + '\n```'            
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
