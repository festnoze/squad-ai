from langchain.tools import tool
from helpers.file_helper import file
from helpers.llm_helper import Llm
from langgraph.prebuilt.tool_executor import ToolExecutor
from langchain.tools.render import format_tool_to_openai_function
from langchain.agents import Tool
from langchain_experimental.utilities import PythonREPL
from models.question_analysis import QuestionAnalysis, QuestionAnalysisPydantic
from prefect import flow, task
from prefect.task_runners import ConcurrentTaskRunner
from services.rag_service import RAGService
import langchains.langchain_rag as langchain_rag


class RagInferencePipeline:
    
    def __init__(self, rag: RAGService, tools: list = None):
        self.rag = rag
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
    def run(self, query: str, include_bm25: bool = False, give_score = True):
        
        # Pre-treatment query: translate, search for meta-data
        analysed_query, metadata, guardrails_result = self.rag_pre_treatment(query)
        
        if not guardrails_result:
            print("Query rejected by guardrails")
            return "Cannot answer this question"

        # Data Retrieval subflow (runs in parallel for RAG and BM25)
        retrieved_chunks, bm25_chunks = self.rag_hybrid_retrieval(analysed_query, metadata, include_bm25, give_score)

        # Augmented Answer Generation subflow
        response = self.rag_augmented_answer_generation(retrieved_chunks, bm25_chunks)

        # Post-treatment subflow
        final_response = self.rag_post_treatment(response)

        return final_response
    
    # Pre-treatment subflow
    @flow(task_runner=ConcurrentTaskRunner())  # Allows parallelism
    def rag_pre_treatment(self, query):
        guardrails_result = self.guardrails_query_analysis.submit(query)
        questionAnalysis = self.analyse_query_language.submit(query)
        metadata = self.extract_explicit_metadata.submit(questionAnalysis.translated_question)

        # Wait for tasks completion
        guardrails_result = guardrails_result.result()
        questionAnalysis = questionAnalysis.result()   
        metadata = metadata.result()     

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
        if questionAnalysis.detected_language.__contains__("english"):
            questionAnalysis.translated_question = question
        return QuestionAnalysis(**questionAnalysis)
    
    def extract_explicit_metadata(self, question):
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
        return question,filters

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

    # Data Retrieval subflow with parallel RAG and BM25 retrieval
    @flow(task_runner=ConcurrentTaskRunner())
    def rag_hybrid_retrieval(self, analysed_query: QuestionAnalysis, include_bm25_retieval: bool = False, give_score: bool = True):
       
        retrieved_chunks = self.rag_retrieval.submit(analysed_query)
        if include_bm25_retieval:
            bm25_chunks = self.bm25_retrieval.submit(analysed_query, give_score)

        retrieved_chunks = retrieved_chunks.result()
        bm25_chunks = bm25_chunks.result() if include_bm25_retieval else []
        retained_chunks = hybrid_chunks_selection(retrieved_chunks, bm25_chunks)
        return retained_chunks
        
    @task
    def rag_retrieval(self, query, filters, give_score):
        retrieved_chunks = langchain_rag.retrieve(self.rag.llm, self.vectorstore, query, None, filters, give_score, 10, 0.2, 2)
        return retrieved_chunks
    
    @task
    def bm25_retrieval(query, give_score, filters, k = 3):
        if filters:
            bm25_retriever = langchain_rag.build_bm25_retriever([doc for doc in self.langchain_documents if RAGService.filters_predicate(doc, filters)], len(retrieved_chunks))
        bm25_retriever.k = k
        bm25_retrieved_chunks = bm25_retriever.invoke(query)
        return bm25_retrieved_chunks

    # Augmented answer generation subflow
    @flow
    def rag_augmented_answer_generation(self, retrieved_chunks, bm25_chunks):
        @task
        def response_generation(retrieved_chunks, bm25_chunks):
            # Combine RAG and BM25 chunks and generate a response
            return f"Generated response from {retrieved_chunks + bm25_chunks}"

        # Generate response
        return response_generation(retrieved_chunks, bm25_chunks)

    # Post-treatment subflow
    @flow
    def rag_post_treatment(self, response):
        @task
        def response_post_treatment(response):
            # Post-treatment logic
            return f"Post-treated response: {response}"

        # Post-process the response
        return response_post_treatment(response)