from langchain.tools import tool
from langgraph.prebuilt.tool_executor import ToolExecutor
from langchain.tools.render import format_tool_to_openai_function
from langchain.agents import Tool
from langchain_experimental.utilities import PythonREPL
from prefect import flow, task
from prefect.task_runners import ConcurrentTaskRunner
from langchain_core.documents import Document

from helpers.file_helper import file
from helpers.llm_helper import Llm
from models.logical_operator import LogicalOperator
from models.question_analysis import QuestionAnalysis, QuestionAnalysisPydantic
from services.rag_service import RAGService
import langchains.langchain_rag as langchain_rag

class RagInferencePipeline:
    
    def __init__(self, rag: RAGService, tools: list = None):
        self.rag: RAGService = rag
        self.tools = tools

        if tools and any(tools):
            python_repl = PythonREPL()
            repl_tool = Tool(
                name="python_repl",
                description="A Python shell. Use this to execute python commands. Input should be a valid python command. If you want to see the output of a value, you should print it out with `print(...)`.",
                func=python_repl.run,
            )

            # Pass the tool to the agent supervisor & to the tool executor
            all_tools = [repl_tool]
            
            additionnal_tools = [format_tool_to_openai_function(t) for t in tools] #TODO: check compatibility out of OpenAI
            all_tools.extend(additionnal_tools)
            self.rag.llm = self.rag.llm.bind_functions(all_tools)
            self.tool_executor = ToolExecutor(all_tools)


    # Main flow
    @flow(task_runner=ConcurrentTaskRunner())
    def run(self, query: str, include_bm25_retrieval: bool = False, give_score = True):
        
        # Pre-treatment query: translate, search for meta-data
        analysed_query, metadata, guardrails_result = self.rag_pre_treatment(query)
        
        if not guardrails_result:
            print("Query rejected by guardrails")
            return "Cannot answer this question"

        # Data Retrieval subflow (runs in parallel for RAG and BM25)
        retrieved_chunks = self.rag_hybrid_retrieval(analysed_query, metadata, include_bm25_retrieval, give_score)

        # Augmented Answer Generation subflow
        response = self.rag_augmented_answer_generation(retrieved_chunks, analysed_query)

        # Post-treatment subflow
        final_response = self.rag_post_treatment(response)

        return final_response, retrieved_chunks
    
    # Pre-treatment subflow
    @flow(task_runner=ConcurrentTaskRunner())  # Allows parallelism
    def rag_pre_treatment(self, query):
        guardrails_result = self.guardrails_query_analysis.submit(query)
        questionAnalysis = self.analyse_query_language(query)
        extracted_metadata = self.extract_explicit_metadata(questionAnalysis.translated_question)

        
        questionAnalysis.translated_question = extracted_metadata[0].strip()
        metadata = extracted_metadata[1]

        guardrails_result = guardrails_result.result()
        return questionAnalysis, metadata, guardrails_result
    
    @task
    def guardrails_query_analysis(self, query) -> bool:
        # Logic for guardrails analysis (returns True if OK, False if rejected)
        if "bad query" in query:  # Example check
            return False
        return True
    
    @task
    def analyse_query_language(self, question):
        prefilter_prompt = file.get_as_str("prompts/rag_language_detection_query.txt", remove_comments= True)
        prefilter_prompt = prefilter_prompt.replace("{question}", question)
        prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(prefilter_prompt, QuestionAnalysisPydantic, QuestionAnalysis)
        response = Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks("RAG prefiltering", [self.rag.llm, self.rag.llm], output_parser, 10, *[prompt_for_output_parser])
        questionAnalysis = response[0]
        questionAnalysis['question'] = question
        if questionAnalysis['detected_language'].__contains__("english"):
            questionAnalysis['translated_question'] = question
        return QuestionAnalysis(**questionAnalysis)
    
    @task
    def extract_explicit_metadata(self, question) -> tuple[str, dict]:
        filters = {}
        if self.has_manual_filters(question):
            filters, question = self.extract_manual_filters(question)
        else:
            filters = {
                "$and": [
                    {"functional_type": "Controller"},
                    {"summary_kind": "method"}
                ]
            }        
        return question, filters

    def has_manual_filters(self, question: str) -> bool:
        return  question.__contains__("filters:") or question.__contains__("filtres :")
    
    def extract_manual_filters(self, question: str) -> tuple[dict, str]:
        filters = {}
        if question.__contains__("filters:"):
            filters_str = question.split("filters:")[1]
            question = question.split("filters:")[0]
        elif question.__contains__("filtres :"):
            filters_str = question.split("filtres :")[1]
            question = question.split("filtres :")[0]
        filters_str = filters_str.strip()
        filters = self.get_filters_from_str(filters_str)
        return filters, question
    
    def get_filters_from_str(self, filters_str: str) -> dict:
        filters = []
        filters_list = filters_str.lower().split(',')

        for filter in filters_list:
            # functional_type: Controller, Service, Repository, ...
            if "controller" in filter or "service" in filter or "repository" in filter:
                # Ensure the first letter is uppercase
                functional_type = filter.strip().capitalize()
                filters.append({"functional_type": functional_type})
            # summary_kind: class, method, (property, enum_member), ...
            elif "method" in filter or "méthode" in filter:
                filters.append({"summary_kind": "method"})
            elif "class" in filter:
                filters.append({"summary_kind": "class"})

        # If there are more than one filters, wrap in "$and", otherwise return a single filter
        if len(filters) > 1:
            return {"$and": filters}
        elif len(filters) == 1:
            return filters[0]  # Just return the single condition directly
        else:
            return {}  # Return an empty filter if no conditions found

    # Data Retrieval subflow with parallel RAG and BM25 retrieval
    @flow(task_runner=ConcurrentTaskRunner())
    def rag_hybrid_retrieval(self, analysed_query: QuestionAnalysis, metadata, include_bm25_retrieval: bool = False, give_score: bool = True, max_retrived_count: int = 10):
       
        rag_retrieved_chunks = self.rag_retrieval.submit(analysed_query, metadata, give_score, max_retrived_count)
        if include_bm25_retrieval:
            bm25_retrieved_chunks = self.bm25_retrieval.submit(analysed_query, metadata, give_score, max_retrived_count)

        rag_retrieved_chunks = rag_retrieved_chunks.result()
        bm25_retrieved_chunks = bm25_retrieved_chunks.result() if include_bm25_retrieval else []
        retained_chunks = self.hybrid_chunks_selection(rag_retrieved_chunks, bm25_retrieved_chunks, give_score, max_retrived_count)
        return retained_chunks

    @task    
    def hybrid_chunks_selection(self, rag_retrieved_chunks: list[Document], bm25_retrieved_chunks: list[Document] = None, give_score: bool = False, max_retrived_count: int = None):
        if not bm25_retrieved_chunks or not any(bm25_retrieved_chunks):
            return rag_retrieved_chunks
        
        rag_retrieved_chunks.extend([(chunk, 0) for chunk in bm25_retrieved_chunks] if give_score else bm25_retrieved_chunks)
        
        if max_retrived_count:
            if give_score:
                rag_retrieved_chunks = sorted(rag_retrieved_chunks, key=lambda x: x[1], reverse=True)
            rag_retrieved_chunks = rag_retrieved_chunks[:max_retrived_count]

        return rag_retrieved_chunks
    
    @task
    def rag_retrieval(self, analysed_query: QuestionAnalysis, filters, give_score: bool = False, max_retrived_count: int = 10, min_score: float = None, min_retrived_count: int = None):
        retrieved_chunks = self.rag.rag_retrieval(analysed_query.translated_question, None, filters, give_score, max_retrived_count, min_score, min_retrived_count)
        return retrieved_chunks
    
    @task
    def bm25_retrieval(self, query, filters, give_score, k = 3):
        if filters:
            bm25_retriever = langchain_rag.build_bm25_retriever([doc for doc in self.rag.langchain_documents if RagInferencePipeline.filters_predicate(doc, filters)], k)
        bm25_retriever.k = k
        bm25_retrieved_chunks = bm25_retriever.invoke(query)
       
        if give_score:
            score = 0.1
            return [(doc, score) for doc in bm25_retrieved_chunks]
        else:
            return bm25_retrieved_chunks
        
     # Helper function to evaluate filter(s) (handling nested operators)
    @staticmethod
    def filters_predicate(doc, filters, operator=LogicalOperator.AND):
        # If filters is a dictionary (single filter or operator like $and/$or)
        if isinstance(filters, dict):
            if "$and" in filters:
                # Recursively handle $and with multiple conditions
                return RagInferencePipeline.filters_predicate(doc, filters["$and"], LogicalOperator.AND)
            elif "$or" in filters:
                # Recursively handle $or with multiple conditions
                return RagInferencePipeline.filters_predicate(doc, filters["$or"], LogicalOperator.OR)
            else:
                # Handle single key-value filter (field-value pair)
                return all(doc.metadata.get(key) == value for key, value in filters.items())

        # If filters is a list, apply the operator (AND/OR)
        elif isinstance(filters, list):
            if operator == LogicalOperator.AND:
                return all(
                    RagInferencePipeline.filters_predicate(doc, sub_filter, LogicalOperator.AND)
                    for sub_filter in filters
                )
            elif operator == LogicalOperator.OR:
                return any(
                    RagInferencePipeline.filters_predicate(doc, sub_filter, LogicalOperator.OR)
                    for sub_filter in filters
                )
            else:
                raise ValueError(f"Unhandled operator: {operator}")

        return False
    
    
    # Augmented answer generation subflow
    @flow
    def rag_augmented_answer_generation(self, retrieved_chunks: list, questionAnalysis: QuestionAnalysis):
        return self.rag_response_generation(retrieved_chunks, questionAnalysis)

    @task
    def rag_response_generation(self, retrieved_chunks: list, questionAnalysis: QuestionAnalysis):
        # Remove score from retrieved docs
        retrieved_chunks = [doc[0] if isinstance(doc, tuple) else doc for doc in retrieved_chunks]
        return langchain_rag.generate_response_from_retrieved_chunks(self.rag.llm, retrieved_chunks, questionAnalysis)
        
    # Post-treatment subflow
    @flow
    def rag_post_treatment(self, response):
        return self.response_post_treatment(response)
        
    @task
    def response_post_treatment(self, response):
        return response