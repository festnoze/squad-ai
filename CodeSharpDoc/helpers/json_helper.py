import json
import xmltodict

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
    
    def convert_json_to_xml(json_string: str) -> str:
        python_dict=json.loads(json_string)
        xml_string = xmltodict.unparse(python_dict)
        return xml_string  
    