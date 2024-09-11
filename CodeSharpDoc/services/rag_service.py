import json
from typing import Tuple
from helpers.file_already_exists_policy import FileAlreadyExistsPolicy
from helpers.file_helper import file
from helpers.llm_helper import Llm
from langchains.langchain_factory import LangChainFactory
from models.llm_info import LlmInfo
from models.logical_operator import LogicalOperator
from models.question_analysis import QuestionAnalysis, QuestionAnalysisPydantic
from models.rag_struct import RagMethodDesc
from models.structure_desc import StructureDesc
from langchain_core.language_models import BaseChatModel
from langchain_core.documents import Document
#
import langchains.langchain_rag as lrag

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
    
    def delete_vectorstore(self):
        lrag.delete_vectorstore()

    rag_structs_summaries_json_filepath = "outputs/rag_structs_summaries.json"
    
    def build_vectorstore_from(self, data: list, doChunkContent = True)-> int:
        if not data or len(data) == 0:
            return 0
        self.rag_methods_desc = []
        self.vectorstore = lrag.build_vectorstore(data, doChunkContent)
        json_data = json.dumps(data)
        file.write_file(json_data, RAGService.rag_structs_summaries_json_filepath, file_exists_policy= FileAlreadyExistsPolicy.Override)
        return self.vectorstore._collection.count()
    
    def load_vectorstore(self, bm25_results_count: int = 1):
        if not file.file_exists(RAGService.rag_structs_summaries_json_filepath):
            return None
        self.vectorstore = lrag.load_vectorstore()
        
        data = file.read_file(RAGService.rag_structs_summaries_json_filepath)
        json_data = json.loads(data)
        self.langchain_documents = [
            Document(page_content=doc["page_content"], metadata=doc["metadata"]) 
            for doc in json_data
        ]
        self.bm25_retriever = lrag.build_bm25_retriever(self.langchain_documents, bm25_results_count)
        return self.vectorstore._collection.count()

    def import_structures(self, structures: list[StructureDesc]):
        self.structures = structures        
        for struct in structures:
            for method in struct.methods:
                self.rag_methods_desc.append(RagMethodDesc(method.method_name, method.generated_summary, struct.file_path).to_dict())  
        self.vectorstore = lrag.build_vectorstore(self.rag_methods_desc)

    def query(self, question: str, additionnal_context: str = None, include_bm25_retieval = False, give_score = False) -> Tuple[str, str]:
        # pre-filtering: analyse used language and need to RAG retieval
        questionAnalysis = self.prefilter_rag_query(question)
        if not questionAnalysis.detected_language.__contains__("english"):
            question = questionAnalysis.translated_question

        #RAG documents retrieval
        filters = {
            "$and": [
                {"functional_type": "Controller"},
                {"summary_kind": "method"}
            ]
        }
        retrieved_chunks = lrag.retrieve(self.llm, self.vectorstore, question, additionnal_context, give_score, filters)
        
        #BM25 retrieval
        if include_bm25_retieval:
            if filters:
                self.bm25_retriever = lrag.build_bm25_retriever([doc for doc in self.langchain_documents if RAGService.filters_predicate(doc, filters)], len(retrieved_chunks))
            self.bm25_retriever.k = len(retrieved_chunks)
            bm25_retrieved_chunks = self.bm25_retriever.invoke(question)
            retrieved_chunks.extend([(chunk, 0) for chunk in bm25_retrieved_chunks] if give_score else bm25_retrieved_chunks)

        answer = lrag.generate_response_from_retrieved_chunks(self.llm, retrieved_chunks, questionAnalysis)
        return answer, retrieved_chunks

    def prefilter_rag_query(self, question)-> QuestionAnalysis:
        prefilter_prompt = file.get_as_str("prompts/rag_prefiltering_query.txt", remove_comments= True)
        prefilter_prompt = prefilter_prompt.replace("{question}", question)
        prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(prefilter_prompt, QuestionAnalysisPydantic, QuestionAnalysis)
        self.llm_batch_size = 100
        response = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks("RAG prefiltering", [self.llm, self.llm], output_parser, self.llm_batch_size, *[prompt_for_output_parser])
        questionAnalysis = response[0]
        questionAnalysis['question'] = question
        return QuestionAnalysis(**questionAnalysis)
    
    # Helper function to evaluate single filter (handling nested operators)
    def filters_predicate(doc, filters, operator=LogicalOperator.AND):
        # If filters is a dictionary (single filter or operator like $and/$or)
        if isinstance(filters, dict):
            if "$and" in filters:
                # Recursively handle $and with multiple conditions
                return RAGService.filters_predicate(doc, filters["$and"], LogicalOperator.AND)
            elif "$or" in filters:
                # Recursively handle $or with multiple conditions
                return RAGService.filters_predicate(doc, filters["$or"], LogicalOperator.OR)
            else:
                # Handle single key-value filter (field-value pair)
                return all(doc.metadata.get(key) == value for key, value in filters.items())

        # If filters is a list, apply the operator (AND/OR)
        elif isinstance(filters, list):
            if operator == LogicalOperator.AND:
                return all(
                    RAGService.filters_predicate(doc, sub_filter, LogicalOperator.AND)
                    for sub_filter in filters
                )
            elif operator == LogicalOperator.OR:
                return any(
                    RAGService.filters_predicate(doc, sub_filter, LogicalOperator.OR)
                    for sub_filter in filters
                )
            else:
                raise ValueError(f"Unhandled operator: {operator}")

        return False