import json
from typing import List
from pydantic import BaseModel, Field

from helpers.txt_helper import txt
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
        if len(kwargs) > 1 and 'params_list' not in kwargs:
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
        if self.params_list and any(self.params_list):
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
        json_data = txt.fix_invalid_json(json_data)
        data = json.loads(json_data)
        is_list = isinstance(data, list) 
        has_single_prop = len(data) == 1

        if has_single_prop:
            if is_list:
                is_first_param_list = isinstance(data[0], list)
            else:
                is_first_param_list = isinstance(data.keys()[0], list)
        else:
            is_first_param_list = False

        params_docs_list: List[ParameterDocumentation] = []
        
        if is_list and not is_first_param_list:
            params_docs_list = [ParameterDocumentation(param['param_name'], param['param_desc']) for param in data]
        else:
            if is_list:
                for param in data:
                    params_docs_list.append(ParameterDocumentation(param['param_name'], param['param_desc']))
            else:
                for key in data.keys():
                    params_docs_list.append(ParameterDocumentation(data[key]['param_name'], data[key]['param_desc']))
        documentation = MethodParametersDocumentation(params_list=params_docs_list)
        return documentation
        
class MethodParametersDocumentationPydantic(BaseModel):
    params_list: list[ParameterDocumentationPydantic] = Field(description="The list of parameters with their descriptions for a specific method.")