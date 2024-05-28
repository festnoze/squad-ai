from typing import Tuple
from models.rag_struct import RagMethodDesc
from models.structure_desc import StructureDesc
from langchain_core.language_models import BaseChatModel
#
import langchains.langchain_rag as rag

class RAGService:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def import_data(self, data: list):
        self.rag_methods_desc = []
        self.db = rag.build_vectorstore(data)

    def import_structures(self, structures: list[StructureDesc]):
        self.structures = structures        
        for struct in structures:
            for method in struct.methods:
                self.rag_methods_desc.append(RagMethodDesc(method.method_name, method.generated_summary, struct.file_path).to_dict())  
        self.db = rag.build_vectorstore(self.rag_methods_desc)
            

    def query(self, question: str) -> Tuple[str, str]:
        retrived_chunks = rag.retrieve(self.llm, self.db, question)
        msg = rag.generate_response_from_retrieval(self.llm, retrived_chunks, question)
        return msg.content, retrived_chunks
        