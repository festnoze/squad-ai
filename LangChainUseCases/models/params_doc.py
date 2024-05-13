import json
from typing import List

from langchain.tools import tool
from langchain.pydantic_v1 import BaseModel, Field

from models.param_doc import ParameterDocumentation, ParameterDocumentationPydantic

class MethodParametersDocumentation:
    """
    Holds the description of all parameters of a method.
    """
    def __init__(self, **kwargs):
        """
        Initializes the MethodParametersDocumentation object with the given arguments.

        Args:
            **kwargs (dict): A dictionary containing the parameters list as a list of ParameterDocumentation objects, or no parameters to init. an empty object.
        """
        if len(kwargs) > 1:
            raise ValueError('Invalid arguments: accepts either no arguments, or a list of ParameterDocumentation objects, or a dictionary containing parameter name and description.')
        
        self.params_list: List[ParameterDocumentation] = []
        if 'params_list' in kwargs:      
            for param in kwargs['params_list']:
                if type(param) is dict:
                    self.params_list.append(ParameterDocumentation(param['param_name'], param['param_desc']))
                elif type(param) is ParameterDocumentation:
                    self.params_list.append(param)
                else:
                    raise ValueError('Invalid argument type')

    def __str__(self) -> str:
        """
        Returns a string representation of the MethodParametersDocumentation object.

        Returns:
            str: The string representation of the MethodParametersDocumentation object.
        """
        desc = "The method contains the following parameters and their descriptions:\n"
        if self.params_list and len(self.params_list) > 0:
            desc += '\n  * ' + '\n  * '.join([str(param) for param in self.params_list])
        else:
            desc += "No parameter required for the method."
        return desc

    def from_json(json_data: str) -> 'MethodParametersDocumentation':
        """
        Creates a MethodParametersDocumentation object from a JSON string.

        Args:
            json_str (str): The JSON string representing the MethodParametersDocumentation object.

        Returns:
            MethodParametersDocumentation: The MethodParametersDocumentation object created from the JSON string.
        """
        data = json.loads(json_data)
        params_docs_list: List[ParameterDocumentation] = []
        if 'params_list' in data:
            params_docs_list = [ParameterDocumentation(param['param_name'], param['param_desc']) for param in data['params_list']]
        elif 'parameters' in data:
            params_docs_list = [ParameterDocumentation(param['param_name'], param['param_desc']) for param in data['parameters']]
        else:
            params_docs_list = [ParameterDocumentation(param['param_name'], param['param_desc']) for param in data]
        documentation = MethodParametersDocumentation(params_list=params_docs_list)
        return documentation
        
class MethodParametersDocumentationPydantic(BaseModel):
    params_list: list[ParameterDocumentationPydantic] = Field(description="The list of parameters with their descriptions for a specific method.")