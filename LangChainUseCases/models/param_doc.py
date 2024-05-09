from models.base_desc import BaseDesc
import json

class ParameterDocumentation(BaseDesc):
    """
    Represents the documentation for a parameter.
    
    Args:
        param_name (str): The name of the parameter.
        description (str, optional): The description of the parameter.
    """    
    def __init__(self, param_name: str, description: str):
        super().__init__(name=param_name)
        self.param_name = param_name
        self.description = description

class MethodParametersDocumentation(list[ParameterDocumentation]):
    """
    Holds the documentation for all method's parameters.
    """
    def __init__(self, *args: str):
        """
        Initializes the MethodParametersDocumentation object with the given arguments.

        Args:
            *args (str): Variable length arguments representing parameter names and descriptions.
                The arguments should be provided in pairs, where the first argument is the parameter name
                and the second argument is the parameter description.
        """
        super().__init__()
        for i in range(0, len(args), 2):
            param_name = args[i]
            description = args[i+1]
            parameter_doc = ParameterDocumentation(param_name, description)
            self.append(parameter_doc)

