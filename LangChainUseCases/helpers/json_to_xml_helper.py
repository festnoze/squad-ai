import json
import xmltodict

def convert_json_to_xml(json_string: str) -> str:
    python_dict=json.loads(json_string)
    xml_string = xmltodict.unparse(python_dict)
    print("The XML string is:")
    print(xml_string)
    return xml_string