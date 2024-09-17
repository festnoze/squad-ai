import json
import time
from typing import Tuple
from helpers.file_already_exists_policy import FileAlreadyExistsPolicy
from helpers.file_helper import file
from helpers.llm_helper import Llm
from helpers.txt_helper import txt
from langchains.langchain_factory import LangChainFactory
from langchains.langgraph_agent_state import AgentState
from models.llm_info import LlmInfo
from models.logical_operator import LogicalOperator
from models.question_analysis import QuestionAnalysis, QuestionAnalysisPydantic
from models.rag_struct import RagMethodDesc
from models.structure_desc import StructureDesc
from langchain_core.language_models import BaseChatModel
from langchain_core.documents import Document
#
import langchains.langchain_rag as langchain_rag

class RAGService:
    def __init__(self, llm_or_infos):
        if isinstance(llm_or_infos, LlmInfo) or (isinstance(llm_or_infos, list) and any(llm_or_infos) and isinstance(llm_or_infos[0], LlmInfo)):            
            self.llm = LangChainFactory.create_llms_from_infos(llm_or_infos)[0]
        elif isinstance(llm_or_infos, BaseChatModel):
            self.llm = llm_or_infos
        else:
            raise ValueError("Invalid llm_or_infos parameter")
        self.load_vectorstore()

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
    
    def empty_vectorstore(self):
        if self.vectorstore:
            self.vectorstore.reset_collection()
            #langchain_rag.delete_vectorstore_files()

    rag_structs_summaries_json_filepath = "outputs/rag_structs_summaries.json"
    
    def build_vectorstore_from(self, data: list, doChunkContent = True)-> int:
        if not data or len(data) == 0:
            return 0
        self.rag_methods_desc = []
        self.vectorstore = langchain_rag.build_vectorstore(data, doChunkContent)
        json_data = json.dumps(data)
        file.write_file(json_data, RAGService.rag_structs_summaries_json_filepath, file_exists_policy= FileAlreadyExistsPolicy.Override)
        return self.vectorstore._collection.count()
    
    def load_vectorstore(self, bm25_results_count: int = 1):
        if not file.file_exists(RAGService.rag_structs_summaries_json_filepath):
            return None
        self.vectorstore = langchain_rag.load_vectorstore()
        
        data = file.read_file(RAGService.rag_structs_summaries_json_filepath)
        json_data = json.loads(data)
        self.langchain_documents = [
            Document(page_content=doc["page_content"], metadata=doc["metadata"]) 
            for doc in json_data
        ]
        self.bm25_retriever = langchain_rag.build_bm25_retriever(self.langchain_documents, bm25_results_count)
        return self.vectorstore._collection.count()

    def import_structures(self, structures: list[StructureDesc]):
        self.structures = structures        
        for struct in structures:
            for method in struct.methods:
                self.rag_methods_desc.append(RagMethodDesc(method.method_name, method.generated_summary, struct.file_path).to_dict())  
        self.vectorstore = langchain_rag.build_vectorstore(self.rag_methods_desc)

    # def query(self, question: str, additionnal_context: str = None, include_bm25_retieval = False, give_score = False) -> Tuple[str, str]:
    #     inferencePipeline = RagInferencePipeline(self.llm, None)
    #     answer, chunks = inferencePipeline.run(query=question, include_bm25=False, give_score=give_score)
    #     txt.print("Answer: " + Llm.get_llm_answer_content(answer))
    #     return answer, chunks