import json
from typing import Tuple
from helpers.file_already_exists_policy import FileAlreadyExistsPolicy
from helpers.file_helper import file
from models.logical_operator import LogicalOperator
from models.rag_struct import RagMethodDesc
from models.structure_desc import StructureDesc
from langchain_core.language_models import BaseChatModel
from langchain_core.documents import Document
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

    rag_structs_summaries_json_filepath = "outputs/rag_structs_summaries.json"
    
    def build_vectorstore_from(self, data: list, doChunkContent = True):
        self.rag_methods_desc = []
        self.vectorstore = lrag.build_vectorstore(data, doChunkContent)
        json_data = json.dumps(data)
        file.write_file(json_data, RAGService.rag_structs_summaries_json_filepath, file_exists_policy= FileAlreadyExistsPolicy.Override)
        return self.vectorstore._collection.count()
    
    def load_vectorstore(self, bm25_results_count: int):
        self.vectorstore = lrag.load_vectorstore()
        data = file.read_file(RAGService.rag_structs_summaries_json_filepath)
        json_data = json.loads(data)
        langchain_documents = [
            Document(page_content=doc["page_content"], metadata=doc["metadata"]) 
            for doc in json_data
        ]
        self.bm25_retriever = lrag.build_bm25_retriever(langchain_documents, bm25_results_count)
        return self.vectorstore._collection.count()

    def import_structures(self, structures: list[StructureDesc]):
        self.structures = structures        
        for struct in structures:
            for method in struct.methods:
                self.rag_methods_desc.append(RagMethodDesc(method.method_name, method.generated_summary, struct.file_path).to_dict())  
        self.vectorstore = lrag.build_vectorstore(self.rag_methods_desc)

    def query(self, question: str, additionnal_context: str = None, include_bm25_retieval = False, give_score = False) -> Tuple[str, str]:
        filters = {
            "$and": [
                {"functional_type": "Controller"},
                {"summary_kind": "method"}
            ]
        }
        retrieved_chunks = lrag.retrieve(self.llm, self.vectorstore, question, additionnal_context, give_score, filters)
        
        if include_bm25_retieval:
            self.bm25_retriever.k = len(retrieved_chunks)
            bm25_retrieved_chunks = self.bm25_retriever.invoke(question)
            bm25_retrieved_chunks = [doc for doc in bm25_retrieved_chunks if RAGService.filters_predicate(doc, filters, LogicalOperator.AND)]
            retrieved_chunks.extend([(chunk, 0) for chunk in bm25_retrieved_chunks] if give_score else bm25_retrieved_chunks)

        answer = lrag.generate_response_from_retrieved_chunks(self.llm, retrieved_chunks, question)
        return answer, retrieved_chunks
    
    # Helper function to evaluate single filter (handling nested operators)
    def single_filter_or_operator_predicate(doc, filter_dict):
        if isinstance(filter_dict, dict):
            if "$and" in filter_dict:
                return RAGService.filters_predicate(doc, filter_dict["$and"], LogicalOperator.AND)
            elif "$or" in filter_dict:
                return RAGService.filters_predicate(doc, filter_dict["$or"], LogicalOperator.OR)
            else:
                return all(doc.metadata.get(key) == value for key, value in filter_dict.items())
        return False

    # Function to evaluate multiple filters (supports AND/OR logic)
    def filters_predicate(doc, filters, operator=LogicalOperator.AND):
        if operator == LogicalOperator.AND:
            return all(
                RAGService.single_filter_or_operator_predicate(doc, sub_filters)
                for sub_filters in filters
            )
        elif operator == LogicalOperator.OR:
            return any(
                RAGService.single_filter_or_operator_predicate(doc, filter_dict)
                for filter_dict in filters
            )
        else:
            raise ValueError(f"Unhandled operator: {operator}")