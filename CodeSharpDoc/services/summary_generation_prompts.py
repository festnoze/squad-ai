import os
#
from helpers.txt_helper import txt
from helpers.llm_helper import Llm
from models.method_desc import MethodDesc
from models.structure_desc import StructureDesc
from models.structure_types import StructureType

class SummaryGenerationPrompts:    
    ctor_txt = "Take into account that this method is a constructor for the containing class of the same name."
    existing_summary_prompt_txt = "Take into account that this method has the following existing summary: '[existing_summary]'."
    compare_created_summary_with_existing = "After having creating your own summary, you will compare its with the existing one given before, and returns the one which seems the most accurate to describe the method functionnal purpose."
    
    @staticmethod    
    def get_prompt_to_generate_method_summary(method: MethodDesc) -> str:
        output_format = txt.single_line(f"""
                Respect the following format: Your answer must have a direct, conscise and factual style. 
                Your answer must always begin by an action verb, (like: 'Get', 'Retrieve', 'Update', 'Check', etc ...) to describe the aim of the method, 
                then possibly followed by any needed precisions, like: conditions, infos about concerned data, or anything else.
                For example: 'Retrieve the last message for a specified user' is a good formated answer, where as:
                'This method retrieves the last message by user ID' is not formated correctly.""")
        prompt = txt.single_line(f"""
                Analyse method name and the method code to produce a single sentence summary of it's functionnal purpose and behavior 
                with no mention to the method name, its asynchronicity, or its parameters, unless it make sense to explain the method functionnal purpose. 
                {SummaryGenerationPrompts.ctor_txt if method.is_ctor else ""}
                {SummaryGenerationPrompts.existing_summary_prompt_txt.replace("[existing_summary]", method.existing_summary) if method.existing_summary else ""}
                {output_format}             
                The method name is: '{method.method_name}' and its full code is: """)
        
        prompt += Llm.embed_into_code_block('csharp', method.code)
        if method.existing_summary:
            prompt += '\n' + SummaryGenerationPrompts.compare_created_summary_with_existing
        return prompt

        # TODO: see how to rather use code_chunks from method_desc for big methods
        # docs = Summarize.split_text(llm, text, max_tokens)
        # chain = Summarize.splitting_chain(llm)
        # method_summary = Summarize.split_prompt_and_invoke(llm, prompt, 8000)
        # return method_summary
    
    @staticmethod
    def get_prompt_to_generate_parameters_summaries(method: MethodDesc): 
        if not method.params or len(method.params) == 0:
            method_params_str = 'no parameters'
        else:
            method_params_str = ', '.join([item.to_str() for item in method.params])

        # Base prompt w/o json output format spec. (used alone in case of further use of an output parser to convert the LLM response to the specified pydantic json object)
        method_params_summaries_prompt = txt.single_line(f"""\
            The list of parameters is: '{method_params_str}'. We have an existing method named: '{method.method_name}', 
            {SummaryGenerationPrompts.ctor_txt if method.is_ctor else ""} for context, the method purpose is: '{method.generated_summary}'.
            Generate a description for each parameter of the following C# method.""")
        
        # Prompt extension to specify the awaited json output format (used when no output parser is defined)
        json_formatting_spec_prompt = txt.single_line(f"""
            The awaited output should be a json array, with one item by parameter, each item having two keys: 
            - 'param_name': containing the parameter name, 
            - and 'param_desc': containing the description that you have generated of the parameter.""")
        
        return method_params_summaries_prompt, json_formatting_spec_prompt
     
    @staticmethod                   
    def get_prompt_to_generate_method_return_summary(method: MethodDesc) -> str:
        params_list = txt.get_prop_or_key(method.generated_parameters_summaries, 'params_list')
        params_list_str = ' ; '.join([str(item) for item in params_list])
        prompt = txt.single_line(f"""\
            Create a description of the return value of the following C# method.
            Instructions: You always begin with: 'Returns ' then generate a description of the return value. The description must be very short and synthetic (less than 15 words)
            The method name is: '{method.method_name}', {SummaryGenerationPrompts.ctor_txt if method.is_ctor else ""} and to help you understand the purpose of the method, method summary is: '{method.generated_summary}'.
            The list of parameters is: '{params_list_str}'.""")
        return prompt

    @staticmethod                   
    def get_prompt_to_generate_class_summary(class_desc: StructureDesc) -> str:
        prompt = txt.single_line(f"""\
            Instructions: Create a global description for the following C# class (or record) which will be used as its summary.
            The description must be very short and synthetic (one or two sentences maximum).
            The class name is: '{class_desc.struct_name}'.
            To help you understand the global purpose of this class/record, hereinafter is listed all its exposed methods with theirs names and respective summaries :
            - {'\n- '.join([f'{method.method_name}: {method.generated_summary}.' for method in class_desc.methods])}""")
        return prompt

    @staticmethod                   
    def get_prompt_to_generate_enum_summary(enum_desc: StructureDesc) -> str:
        prompt = txt.single_line(f"""\
            Instructions: Create a global description for the following C# enum which will be used as its summary.
            The description must be very short and synthetic (one or two sentences maximum).
            The enum name is: '{enum_desc.struct_name}'.
            To help you understand the global purpose of this class/record, hereinafter is listed all its members with theirs names and respective values:
            - {'\n- '.join([f'{enum_member.member_name} = {str(enum_member.member_value)};' for enum_member in enum_desc.enum_members.members])}""")
        return prompt