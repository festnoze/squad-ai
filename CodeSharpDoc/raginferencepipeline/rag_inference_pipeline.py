from langgraph.prebuilt.tool_executor import ToolExecutor
from langchain.tools.render import format_tool_to_openai_function
from langchain.agents import Tool
from langchain_experimental.utilities import PythonREPL

# Import the task classes from other files
from helpers.execute_helper import Execute
from services.rag_service import RAGService
from raginferencepipeline.rag_pre_treatment_tasks import RAGPreTreatment
from raginferencepipeline.guardrails_tasks import RAGGuardrails
from raginferencepipeline.rag_hybrid_retrieval_tasks import RAGHybridRetrieval
from raginferencepipeline.rag_answer_generation_tasks import RAGAugmentedGeneration
from raginferencepipeline.rag_post_treatment_tasks import RAGPostTreatment

class RagInferencePipeline:
    def __init__(self, rag: RAGService, tools: list = None):
        self.rag: RAGService = rag
        self.tools: list = tools

        if tools and any(tools):
            python_repl = PythonREPL()
            repl_tool = Tool(
                name="python_repl",
                description="Run arbitrary Python code. Get the output with: `print(...)`.",
                func=python_repl.run,
            )
            all_tools = [repl_tool]            
            additionnal_tools = [format_tool_to_openai_function(t) for t in tools] #TODO: check compatibility out of OpenAI
            all_tools.extend(additionnal_tools)
            self.rag.llm = self.rag.llm.bind_functions(all_tools)
            self.tool_executor = ToolExecutor(all_tools)

    # Main workflow
    def run(self, query: str, include_bm25_retrieval: bool = False, give_score=True):

        guardrails_result, (analysed_query, metadata) = Execute.run_parallel( 
            (self.guardrails_query_analysis, (query)), # Guardrails check: query analysis
            (self.rag_pre_treatment, (query)) # Pre-treatment query: translate, search for meta-data
        )
        # # Guardrails check
        # RAGGuardrails.guardrails_query_analysis(query)

        # # Pre-treatment
        # analysed_query, metadata = RAGPreTreatment.rag_pre_treatment(self.rag, query)

        # Data Retrieval
        retrieved_chunks = RAGHybridRetrieval.rag_hybrid_retrieval(self.rag, analysed_query, metadata, include_bm25_retrieval, give_score)

        # Augmented Answer Generation
        response = RAGAugmentedGeneration.rag_augmented_answer_generation(self.rag, retrieved_chunks, analysed_query)

        # Post-treatment
        final_response = RAGPostTreatment.rag_post_treatment(response)

        return final_response, retrieved_chunks
    
    def check_for_guardrails(self, guardrails_future, wait_for_completion:bool) -> bool:
        """Return true if guardrails analysis is done. If so, also raise an error if the query has been rejected"""
        if wait_for_completion:
            guardrails_result = guardrails_future.compute()

        if guardrails_future.done():
            guardrails_result = guardrails_future.result()
            if not guardrails_result:
                raise Exception("Query rejected by guardrails")
            
        return guardrails_future.done()