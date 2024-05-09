
from langchain.pydantic_v1 import BaseModel, Field
from langchain.tools import BaseTool, StructuredTool, tool
from models.param_doc import MethodParametersDocumentation
    
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

    @tool
    def __init__(self, summary: str = "", returns: str = None, example: str = None, *method_parameters_pairs: str):
        """
        Create an instance of CSharpXMLDocumentation with the following parameters:
        - summary: The method's summary.
        - returns: The method's return if any.
        - example: An example of method usage.
        - method_parameters_pairs: Method parameters provided in pairs of strings, where the first argument is the parameter name and the second argument is the parameter description.
        """
        self.summary = summary
        self.returns = returns
        self.example = example
        self.params = MethodParametersDocumentation(method_parameters_pairs)
    
    @tool
    def multiply(a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b

    def __str__(self):
        """
        Returns the C# style XML documentation string.
        """
        doc_str = f"/// <summary>\n/// {self.summary}\n/// </summary>\n"
        for param in self.params:
            doc_str += f"/// <param name=\"{param.param_name}\">{param.description}</param>\n"
        if self.returns:
            doc_str += f"/// <returns>{self.returns}</returns>\n"
        if self.example:
            doc_str += f"/// <example>{self.example}</example>\n"
        return doc_str


# class CSharpXMLDocumentationFactory:
#     @tool
#     def create(summary: str, params: list[ParameterDesc] =None, returns: str =None, example: str =None) -> 'CSharpXMLDocumentation':
#         """
#         Instanciate an object representing a C# method documentation, including: summary, parameters, return and example.

#         :param summary: A string representing the summary section.
#         :param params: A dictionary representing parameter names and descriptions if any, or None if method has no input parameters.
#         :param returns: A string representing the description of the return value or None is not applicable.
#         :param example: A string representing the example section or None is not applicable.
#         """
#         obj = CSharpXMLDocumentation()
#         obj.summary = summary
#         obj.params = params if params is not None else {}
#         obj.returns = returns
#         obj.example = example
#         return obj