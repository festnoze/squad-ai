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
    
    # def convert_json_to_xml(json_string: str) -> str:
    #     python_dict=json.loads(json_string)
    #     xml_string = xmltodict.unparse(python_dict)
    #     return xml_string

    def save_as_json_files(structs: list[StructureDesc], path: str):
        if not os.path.exists(path):
                os.makedirs(path)
        for struct in structs:
            JsonHelper.save_as_json_file(struct, path, struct.name)

    def save_as_json_file(obj: any, file_path: str, file_name: str):
            file_full_path = os.path.join(file_path, file_name + ".json")
            with open(file_full_path, 'w') as file:
                json.dump(obj, file, indent=4)

    def load_structures_from_json(file_path: str):
        with open(file_path, 'r') as file:
            structures = json.load(file)
        return structures
    