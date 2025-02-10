from pydantic import BaseModel

class GenerateSummariesRequestModel(BaseModel):
    files_batch_size: int
    llm_batch_size: int
    code_folder_path: str