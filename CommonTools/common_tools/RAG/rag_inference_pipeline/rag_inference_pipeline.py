from langgraph.prebuilt.tool_executor import ToolExecutor
from langchain.tools.render import format_tool_to_openai_function
from langchain.agents import Tool
from langchain_experimental.utilities import PythonREPL

# Import the task classes from other files
from common_tools.helpers.execute_helper import Execute
from common_tools.RAG.rag_service import RAGService
from common_tools.RAG.rag_inference_pipeline.rag_pre_treatment_tasks import RAGPreTreatment
from common_tools.RAG.rag_inference_pipeline.rag_guardrails_tasks import RAGGuardrails
from common_tools.RAG.rag_inference_pipeline.rag_hybrid_retrieval_tasks import RAGHybridRetrieval
from common_tools.RAG.rag_inference_pipeline.rag_answer_generation_tasks import RAGAugmentedGeneration
from common_tools.RAG.rag_inference_pipeline.rag_post_treatment_tasks import RAGPostTreatment
from common_tools.helpers.file_helper import file
from common_tools.helpers.ressource_helper import Ressource
from common_tools.workflows.workflow_executor import WorkflowExecutor

class RagInferencePipeline:
    def __init__(self, rag: RAGService, default_filters: dict = {}, tools: list = None):
        self.rag: RAGService = rag
        self.default_filters = default_filters
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
            self.rag.inference_llm = self.rag.inference_llm.bind_functions(all_tools)
            self.tool_executor = ToolExecutor(all_tools)

    # Main workflow using the dynamic pipeline
    def run(self, query: str, include_bm25_retrieval: bool = False, give_score=True, format_retrieved_docs_function = None, override_workflow_available_classes:dict = None) -> tuple:
        config = Ressource.get_rag_pipeline_default_config_1()
        if override_workflow_available_classes:
            workflow_available_classes = override_workflow_available_classes
        else:
            workflow_available_classes = {
                    'RAGGuardrails': RAGGuardrails,
                    'RAGPreTreatment': RAGPreTreatment,
                    'RAGHybridRetrieval': RAGHybridRetrieval,
                    'RAGAugmentedGeneration': RAGAugmentedGeneration,
                    'RAGPostTreatment': RAGPostTreatment
                }
        workflow_executor = WorkflowExecutor(config, workflow_available_classes)
        
        kwargs_values = {
            'rag': self.rag,
            'query': query,
            'include_bm25_retrieval': include_bm25_retrieval,
            'give_score': give_score,
            'format_retrieved_docs_function': format_retrieved_docs_function
        }

        answer = workflow_executor.execute_workflow(kwargs_values=kwargs_values)

        return answer[0]

    # Main workflow using the static pipeline
    def run_static_pipeline(self, query: str, include_bm25_retrieval: bool = False, give_score=True, format_retrieved_docs_function = None) -> tuple:
        """Run the full RAG inference pipeline including guardrails"""
        guardrails_result, run_inference_pipeline_results = Execute.run_parallel( 
            (RAGGuardrails.guardrails_query_analysis, (query)), # Guardrails check: query analysis
            (self.run_inference_pipeline, (), {'query': query, 'include_bm25_retrieval': include_bm25_retrieval, 'give_score': give_score, 'format_retrieved_docs_function': format_retrieved_docs_function})
        )

        self.check_for_guardrails(guardrails_result) # todo: could rather be awaited before augmentated generation (cf. diagram)
        final_response, retrieved_chunks = run_inference_pipeline_results
        return final_response, retrieved_chunks
    
    def run_inference_pipeline(self, query: str, include_bm25_retrieval: bool = False, give_score=True, format_retrieved_docs_function = None) -> tuple:
        """Run the full RAG inference pipeline, but without guardrails"""
        # Pre-treatment
        analysed_query, metadata = RAGPreTreatment.rag_pre_treatment(self.rag, query, self.default_filters)

        # Data Retrieval
        retrieved_chunks = RAGHybridRetrieval.rag_hybrid_retrieval(self.rag, analysed_query, metadata, include_bm25_retrieval, give_score)

        # Augmented Answer Generation
        response = RAGAugmentedGeneration.rag_augmented_answer_generation(self.rag, retrieved_chunks, analysed_query, give_score, format_retrieved_docs_function)

        # Post-treatment
        final_response = RAGPostTreatment.rag_post_treatment(response)

        return final_response, retrieved_chunks
    
    def check_for_guardrails(self, guardrails_result:bool):
        """Raise an error if the query has been rejected by guardrails"""
        if not guardrails_result:
            raise Exception("Query rejected by guardrails")