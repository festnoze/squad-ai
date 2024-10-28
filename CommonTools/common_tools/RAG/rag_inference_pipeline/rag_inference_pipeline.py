from typing import Optional, Union
from langgraph.prebuilt.tool_executor import ToolExecutor
from langchain.tools.render import format_tool_to_openai_function
from langchain.agents import Tool
from langchain_experimental.utilities import PythonREPL

# Import the task classes from other files
from common_tools.helpers.execute_helper import Execute
from common_tools.rag.rag_service import RagService
from common_tools.rag.rag_inference_pipeline.rag_pre_treatment_tasks import RAGPreTreatment
from common_tools.rag.rag_inference_pipeline.rag_guardrails_tasks import RAGGuardrails
from common_tools.rag.rag_inference_pipeline.rag_hybrid_retrieval_tasks import RAGHybridRetrieval
from common_tools.rag.rag_inference_pipeline.rag_answer_generation_tasks import RAGAugmentedGeneration
from common_tools.rag.rag_inference_pipeline.rag_post_treatment_tasks import RAGPostTreatment
from common_tools.helpers.ressource_helper import Ressource
from common_tools.helpers.file_helper import file
from common_tools.workflows.workflow_executor import WorkflowExecutor
from common_tools.models.conversation import Conversation

class RagInferencePipeline:
    def __init__(self, rag: RagService, default_filters: dict = {}, metadata_descriptions = None, tools: list = None):
        self.rag: RagService = rag
        self.default_filters = default_filters
        self.metadata_descriptions = metadata_descriptions
        RAGPreTreatment.metadata_infos = metadata_descriptions
        RAGPreTreatment.default_filters = default_filters #only useful for dynamic pipeline, to rethink #todo: think to rather instanciate current class for setting specific filters by app.
        self.tools: list = tools

        if tools and any(tools):
            python_repl = PythonREPL()
            repl_tool = Tool(
                name="python_repl",
                description="Run arbitrary Python code. Get the output with: `print(...)`.",
                func=python_repl.run,
            )
            all_tools = [repl_tool]            
            additionnal_tools = [format_tool_to_openai_function(t) for t in tools]
            all_tools.extend(additionnal_tools)
            self.rag.llm = self.rag.llm.bind_functions(all_tools)
            self.tool_executor = ToolExecutor(all_tools)
    
    #todo: return the sources via an extra parameter
    # Main workflow using the dynamic pipeline
    async def run_pipeline_dynamic_async(self, query: Optional[Union[str, Conversation]], include_bm25_retrieval: bool = False, give_score=True, format_retrieved_docs_function = None, override_workflow_available_classes:dict = None) -> tuple:
        config = Ressource.get_rag_pipeline_default_config_wo_augmented_generation()
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

        guardrails_result, retrieved_chunks = workflow_executor.execute_workflow(kwargs_values=kwargs_values)
        self.check_for_guardrails(guardrails_result[0])
        analysed_query = RAGPreTreatment.bypassed_query_classification(self.rag, query)

        # Perform streaming augmented generation
        async for chunk in RAGAugmentedGeneration.rag_augmented_answer_generation_async(self.rag, query, retrieved_chunks[0], analysed_query, format_retrieved_docs_function):
            yield chunk
    
    # Main workflow using the static pipeline
    async def run_pipeline_static_async(self, query: Optional[Union[str, Conversation]], include_bm25_retrieval: bool = False, give_score=True, format_retrieved_docs_function = None):
        """Run the full hardcoded rag inference pipeline but async and with streaming LLM augmented generation response"""
        # Run both functions in parallel, where the second one is treated as streaming
        async for idx, result in Execute.run_parallel_async(
            (RAGGuardrails.guardrails_query_analysis, (query)),  # Guardrails check: query analysis
            (self.run_static_inference_pipeline_but_guardrails_async, (), {
                'query': query,
                'include_bm25_retrieval': include_bm25_retrieval,
                'give_score': give_score,
                'format_retrieved_docs_function': format_retrieved_docs_function
            }),
            functions_with_streaming_indexes=[1]  # Indicating that 'run_static_inference_pipeline_but_guardrails_async' is a streaming async function
        ):
            if idx == 1:
                # Yield the streaming chunks of inference pipeline
                async for chunk in result:
                    yield chunk
            elif idx == 0:
                # Guardrails result, check it
                self.check_for_guardrails(result)
        
        # # Post-treatment
        # final_response = RAGPostTreatment.rag_post_treatment(guardrails_result, response, query)
        # return final_response 
    
    
    async def run_static_inference_pipeline_but_guardrails_async(self, query:Optional[Union[str, Conversation]], include_bm25_retrieval: bool = False, give_score=True, format_retrieved_docs_function = None):
        """Run the full rag inference pipeline, but without guardrails"""
        # Pre-treatment
        analysed_query, metadata = RAGPreTreatment.rag_static_pre_treatment(self.rag, query, self.default_filters)

        # Data Retrieval
        retrieved_chunks = RAGHybridRetrieval.rag_hybrid_retrieval_langchain(self.rag, query, metadata, include_bm25_retrieval, True, give_score)

        # Augmented Answer Generation
        async for chunk in RAGAugmentedGeneration.rag_augmented_answer_generation_async(self.rag, query, retrieved_chunks, analysed_query, format_retrieved_docs_function):
            yield chunk
    
    def check_for_guardrails(self, guardrails_result:bool):
        """Raise an error if the query has been rejected by guardrails"""
        if not guardrails_result:
            raise Exception("Query rejected by guardrails")