from pydantic import BaseModel

class AnalyseFilesRequestModel(BaseModel):
    files_batch_size: int
    code_folder_path: str