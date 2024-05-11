import json
from typing import List
from models.base_desc import BaseDesc
from langchain.tools import tool

class ParameterDocumentation(BaseDesc):
    """
    Represents the documentation for a parameter.
    
    Args:
        param_name (str): The name of the parameter.
        description (str, optional): The description of the parameter.
    """    
    def __init__(self, param_name: str, param_desc: str):
        super().__init__(name=param_name)
        self.param_name = param_name
        self.param_desc = param_desc

    @staticmethod
    @tool
    def create_parameter_documentation(param_name: str, param_desc: str = None):
        """
        Factory function to create a ParameterDocumentation instance.
        
        Args:
            param_name (str): The name of the parameter.
            description (str, optional): A description of the parameter, defaults to None.
        
        Returns:
            ParameterDocumentation: An instance of ParameterDocumentation.
        """
        return ParameterDocumentation(param_name, param_desc)

class MethodParametersDocumentation():
    """
    Holds the description of all parameters of a method.
    """
    @property
    def params_list(self):
        return self._params_list

    @params_list.setter
    def params_list(self, value):
        if not isinstance(value, List):
            raise TypeError('Expected a list')
        self._params_list = value

    params_list: List[ParameterDocumentation] = []

    def __init__(self, *args: str):
        """
        Initializes the MethodParametersDocumentation object with the given arguments.

        Args:
            *args (str): Variable length arguments representing parameter names and descriptions.
                The arguments should be provided in pairs, where the first argument is the parameter name
                and the second argument is the parameter description.
        """
        self._params_list.__init__()
        for i in range(0, len(args), 2):
            param_name = args[i]
            param_desc = args[i+1]
            parameter_doc = ParameterDocumentation(param_name, param_desc)
            self.append(parameter_doc)

    def __init__(self, *args: ParameterDocumentation):
            """
            Initializes the MethodParametersDocumentation object with the given arguments.

            Args:
                *args (ParameterDocumentation): Variable length arguments representing ParameterDocumentation objects.
            """
            if not args: args = []
            self.params_list.__init__(args)

    def from_json(json_str: str) -> 'MethodParametersDocumentation':
        """
        Creates a MethodParametersDocumentation object from a JSON string.

        Args:
            json_str (str): The JSON string representing the MethodParametersDocumentation object.

        Returns:
            MethodParametersDocumentation: The MethodParametersDocumentation object created from the JSON string.
        """
        return MethodParametersDocumentation(*json.loads(json_str))

    @staticmethod
    def create_parameters_documentation(parameters_documentation: list[ParameterDocumentation]) -> 'MethodParametersDocumentation':
        """
        Factory function to create a ParameterDocumentation instance.

        Args:
            parameters_documentation (list[ParameterDocumentation]): A list of ParameterDocumentation objects representing the parameters.

        Returns:
            MethodParametersDocumentation: An instance of MethodParametersDocumentation containing the provided parameters documentation.

        """
        return MethodParametersDocumentation(parameters_documentation)