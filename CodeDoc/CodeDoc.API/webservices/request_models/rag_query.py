from pydantic import BaseModel

class RagQueryRequestModel(BaseModel):
    query: str
    include_bm25_retrieval: bool = False