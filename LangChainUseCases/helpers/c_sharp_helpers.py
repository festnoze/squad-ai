
from langchain.pydantic_v1 import BaseModel, Field
from langchain.tools import BaseTool, StructuredTool, tool
from models.param_doc import ParameterDocumentation
from models.params_doc import MethodParametersDocumentation
    
# class CSharpXMLDocumentationInput(BaseModel):
#     summary: str = Field(description="A string representing the summary section.")
#     params: int = Field(description="A dictionary representing parameter names and descriptions if any, or None if method has no input parameters.")
#     returns: str = Field(description="A string representing the description of the return value or None is not applicable.")
#     example: str = Field(description="A string representing the example section or None is not applicable.")

# class MultiplyInput(BaseModel):
#     a: int = Field(description="first number")
#     b: int = Field(description="second number")

class CSharpXMLDocumentation:    
    summary: str = ""
    params: MethodParametersDocumentation
    returns: str = None
    example: str = None

    def __init__(self, summary: str = "", returns: str = None, example: str = None, *method_parameters_pairs: str):
        """
        Create an instance of CSharpXMLDocumentation with the following parameters:
        - summary: The method's summary.
        - returns: The method's return if any.
        - example: An example of method usage.
        - method_parameters_pairs: Method parameters provided in pairs of strings, where the first argument is the parameter name and the second argument is the parameter description.
        """
        self.summary: str = summary
        self.params: MethodParametersDocumentation = MethodParametersDocumentation(method_parameters_pairs)
        self.returns: str = returns
        self.example: str = example
        
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
        doc_str = f"/// <summary>\n/// {self.summary}\n/// </summary>\n"
        for param in self.params.params_list:
            doc_str += f"/// <param name=\"{param.param_name}\">{param.param_desc}</param>\n"
        if self.returns:
            doc_str += f"/// <returns>{self.returns}</returns>\n"
        if self.example:
            doc_str += f"/// <example>{self.example}</example>\n"
        return doc_str
    
    @staticmethod
    def get_xml(summary: str, params: MethodParametersDocumentation, returns: str = None, example: str = None):
        """
        Create a C# style XML documentation string from the provided parameters.
        """        
        return str(CSharpXMLDocumentation(summary, params, returns, example))

class CSharpXMLDocumentationFactory:
    @tool
    def create_csharp_method_xml_documentation(summary: str, returns: str =None, example: str =None, *method_parameters_pairs: str) -> CSharpXMLDocumentation:
        """
        Instanciate an object representing a C# method documentation, including: summary, parameters, return and example.

        :param summary: A string representing the description of the method purpose.
        :param returns: A string representing the description of the return value or None is not applicable.
        :param example: A string representing the example section or None is not applicable.
        :param method_parameters_pairs: A list of strings representing the method parameters provided in pairs, where the first argument is the parameter name and the second argument is the parameter description.
        """
        obj = CSharpXMLDocumentation(
            summary = summary,
            returns = returns,
            example = example,
            params_list= [ParameterDocumentation(param_name, description) for param_name, description in zip(method_parameters_pairs[::2], method_parameters_pairs[1::2])]
        )
        return obj