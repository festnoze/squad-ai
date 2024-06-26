from typing import AsyncGenerator
import requests 
from requests.exceptions import HTTPError
import json

from models.struct_summaries_infos import StructSummariesInfos
from models.structure_desc import StructureDesc
# internal import

class code_analyser_client:
    host_uri = "http://localhost:5230"
    controller_subpath = "code-structure"
    #endpoints
    analyse_folder_files_post = "analyse/from-folder"
    add_summaries_files_post = "add-summaries/to-structures"

    @staticmethod
    def parse_and_analyse_code_files(files_paths: list[str]) -> list[StructureDesc]:
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
    
    @staticmethod
    def add_summaries_to_code_files(structures_summaries: list[StructSummariesInfos]) -> None:
        url = f"{code_analyser_client.host_uri}/{code_analyser_client.controller_subpath}/{code_analyser_client.add_summaries_files_post}"        
        headers = {
            'Content-Type': 'application/json'
        }
        data = [structure_summaries.to_dict() for structure_summaries in structures_summaries]

        # print("JSON Payload:")
        # print(json.dumps(data, indent=4))
        # print("-------------------")

        response = requests.post(url, json=data, headers=headers)
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            print(f"Response: {response.text}")
            response.raise_for_status()

        if len(response.content) == 0:
            return
        
        json_response = response.json()
        structure_desc_list = [StructureDesc(**item) for item in json_response]

        return structure_desc_list
    
