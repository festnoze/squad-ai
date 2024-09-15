import json
import os
from helpers.file_already_exists_policy import FileAlreadyExistsPolicy
from helpers.file_helper import file
from helpers.txt_helper import txt
from models.struct_summaries_infos import MethodSummaryInfo, StructSummariesInfos
from models.structure_desc import StructureDesc
from services.code_analyser_client import code_analyser_client
from services.csharp_code_analyser_service import CSharpCodeStructureAnalyser
from services.summary_generation_service import SummaryGenerationService

class AnalysedStructuresHandling:
    
    @staticmethod
    def analyse_code_structures_of_folder_and_save(code_file_path: str, struct_desc_folder_path: str, files_batch_size: int, existing_structs_desc: list[StructureDesc]):  
        paths_and_codes = file.get_files_paths_and_contents(code_file_path, 'cs', 'C# code')
        if any(existing_structs_desc):
            SummaryGenerationService.remove_already_analysed_files(existing_structs_desc, paths_and_codes)

        # Split into batchs code files to analyse
        paths_and_codes_batchs = []
        for i in range(0, len(paths_and_codes), files_batch_size):
            batch = list(paths_and_codes.items())[i:i+files_batch_size]
            paths_and_codes_batchs.append(batch)

        # Process each batch
        for i, paths_and_codes_batch in enumerate(paths_and_codes_batchs):
            paths_and_codes_chunk = dict(paths_and_codes_batch)                
            paths_and_codes_chunk = SummaryGenerationService.remove_auto_generated_files(paths_and_codes_chunk)
            if len(paths_and_codes_chunk) == 0: continue
            structs_to_process = code_analyser_client.parse_and_analyse_code_files(list(paths_and_codes_chunk.keys()), True)
            CSharpCodeStructureAnalyser.chunkify_code_of_classes_methods(structs_to_process)
            #structs_summaries_infos, missing_methods_summaries, missing_structs_summaries = SummaryGenerationService.create_struct_summaries_infos(structs_to_process, False)
            AnalysedStructuresHandling.save_analysed_structures_as_json_files(structs_to_process, struct_desc_folder_path)
            txt.print(f"\nBatch {i+1} of {len(paths_and_codes_batchs)} code files analysed and analysis saved.")
            
        txt.print("\nAll codes files successfully analysed.")
    
    def load_json_structs_from_folder_and_ask_to_replace(folder_path: str):
        existing_structs_desc, json_files = AnalysedStructuresHandling.load_json_structs_desc_from_folder(folder_path)
        if existing_structs_desc:
            print(f"{len(existing_structs_desc)} structures descriptions already exist. We will keep those structures descriptions...")
            update_choice = input("... unless you want to Regenerate them? (r/_) ")
            if update_choice == 'r':
                for json_file in json_files:
                    file.delete_file(json_file)
                existing_structs_desc = []
        return existing_structs_desc
    
    def load_json_structs_desc_from_folder(folder_path: str):
        json_files = file.get_files_paths_and_contents(folder_path, 'json', 'code structure analysis')
        structures_descriptions = []
        for file_path in json_files:
            json_struct_desc = json.loads(json_files[file_path])
            structures_descriptions.append(StructureDesc(**json_struct_desc))
        return structures_descriptions, json_files
        
    def save_analysed_structures_as_json_files(structs: list[StructureDesc], path: str, fail_if_files_exists: bool = True):
        if not os.path.exists(path):
                os.makedirs(path)
        for struct in structs:
            AnalysedStructuresHandling.save_analysed_structures_as_json_file(struct, path, struct.namespace_name + '.' + struct.struct_name)

    def save_analysed_structures_as_json_file(struct: StructureDesc, file_path: str, file_name: str):
            file_full_path = os.path.join(file_path, file_name + ".json")
            json_struct = struct.to_json()
            file.write_file(json_struct, file_full_path, FileAlreadyExistsPolicy.AutoRename)