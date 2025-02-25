
from typing import List
from pydantic import BaseModel, Field
from models.coding_guidelines_rule_model import Coding_Guidelines_Rule_Model, Coding_Guidelines_Rule_ModelPydantic

class Coding_Guidelines_BrokenRule_Model(Coding_Guidelines_Rule_Model):
    def __init__(self, rule_code: str, rule_description: str, target_file: str, target_line: int):
        super().__init__(rule_code, rule_description)
        self.target_file: str = target_file
        self.target_line: int = target_line

    def __str__(self) -> str:
        return super().__str__() + f" (found in file '{self.target_file}' at line {self.target_line})"

class Coding_Guidelines_BrokenRule_ModelPydantic(Coding_Guidelines_Rule_ModelPydantic):
    target_file: str = Field(description="The path of the file in which the violated rule was found.")
    target_line: int = Field(description="The line number in the file where the violated rule was found.")