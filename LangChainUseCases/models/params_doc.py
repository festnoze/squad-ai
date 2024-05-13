import json
from typing import List

from langchain.tools import tool
from langchain.pydantic_v1 import BaseModel, Field

from models.param_doc import ParameterDocumentation, ParameterDocumentationPydantic

class MethodParametersDocumentation:
    """
    Holds the description of all parameters of a method.
    """
    @property
    def params_list(self):
        return self._params_list

    @params_list.setter
    def params_list(self, value):
        if not isinstance(value, List[ParameterDocumentation]):
            raise TypeError('Expected a list')
        self._params_list = value

    params_list: List[ParameterDocumentation] = []

    # def __init__(self, *parameters_names_and_descriptions: str):
    #     """
    #     Initializes the MethodParametersDocumentation object with the given arguments.

    #     Args:
    #         *parameters_names_and_descriptions (str): arguments containing each parameter's name and description for a given method.
    #             The arguments should be provided in pairs, where the first argument is the parameter name
    #             and the second argument is the parameter description.
    #     """
    #     self._params_list.__init__()
    #     for i in range(0, len(parameters_names_and_descriptions), 2):
    #         param_name = parameters_names_and_descriptions[i]
    #         param_desc = parameters_names_and_descriptions[i+1]
    #         parameter_doc = ParameterDocumentation(param_name, param_desc)
    #         self.append(parameter_doc)

    def __init__(self, *params_docs: ParameterDocumentation):
        """
        Initializes the MethodParametersDocumentation object with the given arguments.

        Args:
            *params_docs (ParameterDocumentation): Variable length arguments representing ParameterDocumentation objects.
        """
        if not params_docs: params_docs = []
        self.params_list.__init__(params_docs)

    def __init__(self, **kwargs):
        items = kwargs.items()
        if 'params_list' not in kwargs or len(kwargs) > 1:
            raise ValueError('Invalid arguments')
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
        else:
            params_docs_list = [ParameterDocumentation(param['param_name'], param['param_desc']) for param in data]
        documentation = MethodParametersDocumentation(*params_docs_list)
        return documentation

    @staticmethod
    @tool
    def create_method_parameters_documentation(*parameters_names_and_descriptions: str):
        """
        Factory function to create a ParameterDocumentation instance.

        Args:
            *parameters_names_and_descriptions (str): arguments contains alternalively parameter's name then parameter's description for each parameters of a method.
                The arguments should be provided in pairs, where the first argument is the parameter name
                and the second argument is the parameter description.

        Returns:
            MethodParametersDocumentation: An instance of MethodParametersDocumentation containing the provided parameters documentation.

        """
        return MethodParametersDocumentation(*parameters_names_and_descriptions)
    
    @staticmethod
    def create_parameters_documentation_from_dict(input: dict) -> 'MethodParametersDocumentation':
        params_docs_list = []
        for param in input['params_list']:
            param_doc = ParameterDocumentation(param['param_name'], param['param_desc'])
            params_docs_list.append(param_doc)
        return MethodParametersDocumentation(*params_docs_list)
    
class MethodParametersDocumentationPydantic(BaseModel):
    params_list: list[ParameterDocumentationPydantic] = Field(description="The list of parameters with their descriptions for a specific method.")