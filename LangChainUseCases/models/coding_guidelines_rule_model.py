
from typing import List
from pydantic import BaseModel, Field

class Coding_Guidelines_Rule_Model:
    """Defines a rule to be respected by all code reviewed during the code review process."""
    def __init__(self, rule_code: str, rule_description: str):
        self.rule_code: str = rule_code
        self.rule_description: str = rule_description

    def __str__(self) -> str:
        return f"{self.rule_code}: {self.rule_description}"

class Coding_Guidelines_Rules_Model:
    def __init__(self, **kwargs):
        self.rules: List[Coding_Guidelines_Rule_Model] = []
        for rule_code in kwargs:
            if type(rule_code) is dict:
                self.rules.append(Coding_Guidelines_Rule_Model(rule_code['rule_code'], rule_code['rule_description']))
            elif type(rule_code) is Coding_Guidelines_Rule_Model:
                self.rules.append(rule_code)
            else:
                self.rules.append(Coding_Guidelines_Rule_Model(rule_code, kwargs[rule_code]))

    def __str__(self) -> str:
        desc = "The following ruleset compose the company guidelines to be respected during the code review process:\n"
        if self.rules and len(self.rules) > 0:
            desc += '\n  * ' + '\n  * '.join([str(rule) for rule in self.rules])
        else:
            desc += "No rules defined."
        return desc

class Coding_Guidelines_Rule_ModelPydantic(BaseModel):
    rule_code: str = Field(description="The code of the rule that was violated by the reviewed code during the code review process.")
    rule_description: str = Field(description="The code of the rule that was violated by the reviewed code during the code review process.")
