import json
import os

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
    
    def load_from_json(file_path: str, encoding='utf-8-sig'):
        if not os.path.exists(file_path):
            return None
        with open(file_path, 'r', encoding=encoding) as file_handler:
            content = json.load(file_handler)
        return content
    