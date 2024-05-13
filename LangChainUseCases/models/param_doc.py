from models.base_desc import BaseDesc

from langchain.tools import tool
from langchain.pydantic_v1 import BaseModel, Field

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

    def __str__(self):
        return f"Parameter Name: '{self.param_name}', Description: '{self.param_desc}'" 
    
    def to_json(self):
        return {
            "param_name": self.param_name,
            "param_desc": self.param_desc
        }

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

class ParameterDocumentationPydantic(BaseModel):
    param_name: str = Field(description="The name of the parameter (it's always a single word. Also exclude the type of the parameter which may come firstly)")
    param_desc: str = Field(description="The generated description for the parameter")
