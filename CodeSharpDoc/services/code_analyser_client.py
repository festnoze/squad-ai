from typing import AsyncGenerator
import requests 
from requests.exceptions import HTTPError
import json

from models.structure_desc import StructureDesc
# internal import

class code_analyser_client:
    host_uri = "http://localhost:5230"
    controller_subpath = "code-structure"
    #endpoints
    analyse_folder_files_post = "from-folder"

    def get_folder_files_code_structures(folder_path: str, existing_structs_desc: list[StructureDesc]) -> list[StructureDesc]:
        url = f"{code_analyser_client.host_uri}/{code_analyser_client.controller_subpath}/{code_analyser_client.analyse_folder_files_post}"        
        headers = {
            'accept': 'text/plain',
            'Content-Type': 'application/json'
        }
        folder_path = folder_path.replace("\\", "/")
        data = folder_path

        response = requests.post(url, json=data, headers=headers)

        if response.status_code != 200:
            response.raise_for_status()

        json_response = response.json()
        structure_desc_list = [StructureDesc(**item) for item in json_response]
        loaded_structs_count = len(structure_desc_list)

        # remove existing structures
        for struct in existing_structs_desc:
            structure_desc_list = [item for item in structure_desc_list if item.name != struct.name]

        removed_structs_count = loaded_structs_count - len(structure_desc_list)
        print(f"Loaded {loaded_structs_count} structures, including {removed_structs_count} already described.")
        
        return structure_desc_list
    
