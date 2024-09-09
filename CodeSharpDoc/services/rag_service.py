import json
from typing import Tuple
from helpers.file_helper import file
from models.rag_struct import RagMethodDesc
from models.structure_desc import StructureDesc
from langchain_core.language_models import BaseChatModel
#
import langchains.langchain_rag as lrag

class RAGService:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def get_documents_to_vectorize_from_loaded_analysed_structures(self, struct_desc_folder_path: str) -> list[str]:
        docs: list[str] = []
        structs_str = file.get_files_contents(struct_desc_folder_path, 'json')
        for struct_str in structs_str:
            struct = json.loads(struct_str)
            summary = struct['generated_summary'] if hasattr(struct, 'generated_summary') and getattr(struct, 'generated_summary') else struct['existing_summary']
            if summary:
                doc = self.build_document(content=summary, metadata= {'struct_type': struct['struct_type'], 'struct_name': struct['struct_name'], 'namespace': struct['namespace_name'], 'summary_kind': 'method', 'functional_type': struct['functional_type'] })
                docs.append(doc)
            for method in struct['methods']:
                summary = method['generated_summary'] if hasattr(method, 'generated_summary') and getattr(method, 'generated_summary') else method['existing_summary']
                if summary:
                    doc = self.build_document(content=summary, metadata= {'struct_type': struct['struct_type'], 'struct_name': struct['struct_name'], 'method_name': method['method_name'], 'namespace': struct['namespace_name'], 'summary_kind': 'method', 'functional_type': struct['functional_type'] })
                    docs.append(doc)
        return docs
    
    def build_document(self, content: str, metadata: dict):
        return {'page_content': content, 'metadata': metadata}
    
    def delete_vectorstore(self):
        lrag.delete_vectorstore()

    rag_structs_summaries_csv_filepath = "outputs/rag_structs_summaries.csv"
    
    def build_vectorstore_from(self, data: list, doChunkContent = True):
        self.rag_methods_desc = []
        self.vectorstore = lrag.build_vectorstore(data, doChunkContent)
        file.write_csv(RAGService.rag_structs_summaries_csv_filepath, data)
        return self.vectorstore._collection.count()
    
    def load_vectorstore(self, bm25_results_count: int):
        self.vectorstore = lrag.load_vectorstore()
        data = file.read_csv(RAGService.rag_structs_summaries_csv_filepath)
        data = [doc[0] for doc in data] # CSV is single column
        self.bm25_retriever = lrag.build_bm25_retriever(data, bm25_results_count)
        return self.vectorstore._collection.count()

    def import_structures(self, structures: list[StructureDesc]):
        self.structures = structures        
        for struct in structures:
            for method in struct.methods:
                self.rag_methods_desc.append(RagMethodDesc(method.method_name, method.generated_summary, struct.file_path).to_dict())  
        self.vectorstore = lrag.build_vectorstore(self.rag_methods_desc)

    def query(self, question: str, additionnal_context: str = None, include_bm25_retieval = False) -> Tuple[str, str]:
        retrived_chunks = lrag.retrieve(self.llm, self.vectorstore, question, additionnal_context)
        if include_bm25_retieval:
            bm25_retrived_chunks = self.bm25_retriever.invoke(question)
            retrived_chunks.extend(bm25_retrived_chunks)

        answer = lrag.generate_response_from_retrieval(self.llm, retrived_chunks, question)
        return answer, retrived_chunks
    
        