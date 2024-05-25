from models.params_doc import MethodParametersDocumentation

class CSharpHelper:    
    @staticmethod
    def remove_existing_summaries_from_all_files(paths_and_codes: dict):
        for file_path, code in paths_and_codes.items():
            lines = code.splitlines()
            lines = [line for line in lines if not line.strip().startswith('///')]
            paths_and_codes[file_path] = '\n'.join(lines)

class CSharpXMLDocumentation:    
    summary: str = ""
    params: MethodParametersDocumentation
    returns: str = None
    example: str = None
    def __init__(self, summary: str = "", parameters_docs: MethodParametersDocumentation = None, returns: str = None, example: str = None):
        """
        Create an instance of CSharpXMLDocumentation with the following parameters:
        - summary: The method's summary.
        - parameters: A list of ParameterDocumentation objects representing the method's parameters.
        - returns: The method's return if any.
        - example: An example of method usage if any.
        """
        self.summary: str = summary
        self.params: MethodParametersDocumentation = parameters_docs
        self.returns: str = returns
        self.example: str = example

    def __str__(self):
        """
        Returns the C# style XML documentation string.
        """
        doc_str = ""        
        try:
            doc_str =f"/// <summary>\n/// {self.summary.replace('\n', '\n/// ')}\n/// </summary>\n"
            for param in self.params.params_list:
                doc_str += f"/// <param name=\"{param.param_name}\">{param.param_desc}</param>\n"
            if self.returns:
                doc_str += f"/// <returns>{self.returns}</returns>\n"
            if self.example:
                doc_str += f"/// <example>{self.example}</example>\n"
        except:
            pass
        return doc_str
    
    def to_xml(self):
        """
        Create a C# style XML documentation string from the provided parameters.
        """        
        return str(self)

# class CSharpXMLDocumentationFactory:
#     @tool
#     def create_csharp_method_xml_documentation(summary: str, returns: str =None, example: str =None, *method_parameters_pairs: str) -> CSharpXMLDocumentation:
#         """
#         Instanciate an object representing a C# method documentation, including: summary, parameters, return and example.

#         :param summary: A string representing the description of the method purpose.
#         :param returns: A string representing the description of the return value or None is not applicable.
#         :param example: A string representing the example section or None is not applicable.
#         :param method_parameters_pairs: A list of strings representing the method parameters provided in pairs, where the first argument is the parameter name and the second argument is the parameter description.
#         """
#         obj = CSharpXMLDocumentation(
#             summary = summary,
#             returns = returns,
#             example = example,
#             params_list= [ParameterDocumentation(param_name, description) for param_name, description in zip(method_parameters_pairs[::2], method_parameters_pairs[1::2])]
#         )
#         return obj