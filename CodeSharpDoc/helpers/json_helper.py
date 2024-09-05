import json
import os

from models.structure_desc import StructureDesc
#import xmltodict

class JsonHelper:
    def fix_invalid_json(json_str: str) -> str:
        if JsonHelper.validate_json(json_str):
            return json_str
        
        # embed into a json array
        json_str = '[' + json_str + ']'
        return json_str
            
    def validate_json(json_str: str) -> bool:
        try:
            json.loads(json_str)
            return True
        except json.JSONDecodeError as e:
            return False
    
    def load_structures_from_json(file_path: str):
        with open(file_path, 'r') as file_handler:
            structures = json.load(file_handler)
        return structures
    