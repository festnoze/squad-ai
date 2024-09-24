import json
from typing import List
from langchain.pydantic_v1 import BaseModel, Field

from common_tools.helpers.txt_helper import txt
from models.coding_guidelines_broken_rule_model import Coding_Guidelines_BrokenRule_Model, Coding_Guidelines_BrokenRule_ModelPydantic

class Coding_Guidelines_BrokenRules_Model:
    """
    Holds the list of found broken rules during the code review process.
    """
    def __init__(self, **kwargs):
        """
        Initializes the BrokenRulesCodeReviewModel object with the given arguments.

        Args:
            **kwargs (dict): A dictionary containing the list of broken rules found during the code review process.
        """
        if len(kwargs) > 1:
            raise ValueError('Invalid arguments: accepts either no arguments, or a list of broken rules.')
        
        self.broken_rules: List[Coding_Guidelines_BrokenRule_Model] = []
        if 'broken_rules' in kwargs:      
            for param in kwargs['broken_rules']:
                if type(param) is dict:
                    self.broken_rules.append(Coding_Guidelines_BrokenRule_Model(param['rule_code'], param['rule_description'], param['target_file'], param['target_line']))
                elif type(param) is Coding_Guidelines_BrokenRule_Model:
                    self.broken_rules.append(param)
                else:
                    raise ValueError('Invalid argument type')

    def __str__(self) -> str:
        """
        Returns a string representation of the BrokenRulesCodeReviewModel object.

        Returns:
            str: The string representation of the BrokenRulesCodeReviewModel object.
        """
        desc = "The reviewed code contains the following rules violations:\n"
        if self.broken_rules and len(self.broken_rules) > 0:
            desc += '\n  * ' + '\n  * '.join([str(broken_rule) for broken_rule in self.broken_rules])
        else:
            desc += "No violated rules found."
        return desc

    def from_json(json_data: str) -> 'Coding_Guidelines_BrokenRules_Model':
        """
        Creates a BrokenRulesCodeReviewModel object from a JSON string.

        Args:
            json_str (str): The JSON string representing the BrokenRulesCodeReviewModel object.

        Returns:
            BrokenRulesCodeReviewModel: The BrokenRulesCodeReviewModel object created from the JSON string.
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

        broken_rules: List[Coding_Guidelines_BrokenRule_Model] = []
        
        if is_list and not is_first_param_list:
            broken_rules = [Coding_Guidelines_BrokenRule_Model(param['param_name'], param['param_desc']) for param in data]
        else:
            if is_list:
                for param in data:
                    broken_rules.append(Coding_Guidelines_BrokenRule_Model(param['param_name'], param['param_desc']))
            else:
                for key in data.keys():
                    broken_rules.append(Coding_Guidelines_BrokenRule_Model(data[key]['param_name'], data[key]['param_desc']))
        documentation = Coding_Guidelines_BrokenRules_Model(broken_rules=broken_rules)
        return documentation
        
class Coding_Guidelines_BrokenRules_ModelPydantic(BaseModel):
    broken_rules: list[Coding_Guidelines_BrokenRule_ModelPydantic] = Field(description="The list of broken rules found during the code review process.")