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

    def post_analyse_folder_code_files(folder_path: str):
        url = f"{code_analyser_client.host_uri}/{code_analyser_client.controller_subpath}/{code_analyser_client.analyse_folder_files_post}"        
        headers = {
            'accept': 'text/plain',
            'Content-Type': 'application/json'
        }
        folder_path = folder_path.replace("\\", "/")
        data = folder_path

        response = requests.post(url, json=data, headers=headers)

        if response.status_code == 200:
            json_response = response.json()
            structure_desc_list = [StructureDesc(**item) for item in json_response]
            return structure_desc_list
        else:
            response.raise_for_status()
    
