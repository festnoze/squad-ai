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

    @staticmethod
    def analyse_code_structures_of(files_paths: list[str]) -> list[StructureDesc]:
        url = f"{code_analyser_client.host_uri}/{code_analyser_client.controller_subpath}/{code_analyser_client.analyse_folder_files_post}"        
        headers = {
            'accept': 'text/plain',
            'Content-Type': 'application/json'
        }
        data = [file_path.replace("\\", "/") for file_path in files_paths]

        response = requests.post(url, json=data, headers=headers)

        if response.status_code != 200:
            response.raise_for_status()

        json_response = response.json()
        structure_desc_list = [StructureDesc(**item) for item in json_response]

        return structure_desc_list
    
