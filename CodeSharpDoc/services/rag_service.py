import json
from typing import Tuple
from helpers.file_helper import file
from models.rag_struct import RagMethodDesc
from models.structure_desc import StructureDesc
from langchain_core.language_models import BaseChatModel
#
import langchains.langchain_rag as rag

class RAGService:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def load_structures_summaries(self, struct_desc_folder_path: str):
        docs = []
        structs_str = file.get_files_contents(struct_desc_folder_path, 'json')
        for struct_str in structs_str:
            struct = json.loads(struct_str)
            for method in struct['methods']:
                desc = f"In {struct['struct_type']} '{struct['struct_name']}', method named: '{method['method_name']}' does: '{method['generated_summary']}'"
                docs.append(desc)
        return docs

    def build_vectorstore_from(self, data: list):
        self.rag_methods_desc = []
        self.db = rag.build_vectorstore(data)
        return self.db._collection.count()
    
    def load_vectorstore(self):
        self.db = rag.load_vectorstore()
        return self.db._collection.count()

    def import_structures(self, structures: list[StructureDesc]):
        self.structures = structures        
        for struct in structures:
            for method in struct.methods:
                self.rag_methods_desc.append(RagMethodDesc(method.method_name, method.generated_summary, struct.file_path).to_dict())  
        self.db = rag.build_vectorstore(self.rag_methods_desc)
            

    def query(self, question: str, additionnal_context: str = None) -> Tuple[str, str]:
        retrived_chunks = rag.retrieve(self.llm, self.db, question, additionnal_context)
        msg = rag.generate_response_from_retrieval(self.llm, retrived_chunks, question)
        return msg.content, retrived_chunks
    
        