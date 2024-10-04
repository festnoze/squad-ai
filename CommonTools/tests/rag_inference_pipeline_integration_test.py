from common_tools.RAG.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
from common_tools.RAG.rag_service import RAGService
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.models.llm_info import LlmInfo
from common_tools.models.embedding_type import EmbeddingModel

class TestRagInferencePipelineIntegration:

    def setup_method(self):
        # Set up the necessary LLM information for the RAGService
        llms_infos = []
        llms_infos.append(
            LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4o", timeout=80, temperature=0.1)
        )
        
        # Initialize RAGService with the specified embedding model
        self.rag_service = RAGService(llms_infos, EmbeddingModel.OpenAI_TextEmbedding3Small)
        
        # Instantiate RagInferencePipeline with the RAG service
        self.inference = RagInferencePipeline(self.rag_service)

    def test_inference_pipeline_with_bm25_retrieval(self):
        # Define the query for the test
        query = "Quelles sont les formations en RH ?"
        
        # Run the inference pipeline with BM25 retrieval and formatting function
        response, sources = self.inference.run(
            query, 
            include_bm25_retrieval=True, 
            give_score=True, 
            format_retrieved_docs_function=None
        )

        # Assertions to verify that the response and sources are valid
        assert isinstance(response, str), "The response should be a string"
        assert isinstance(sources, list), "The sources should be a list"
        assert len(sources) > 0, "There should be at least one source retrieved"
        assert "Paris" in response, "The response should mention the capital of France"

    def test_inference_pipeline_without_bm25_retrieval(self):
        # Define the query for the test
        query = "Explain the concept of AI."

        # Run the inference pipeline without BM25 retrieval
        response, sources = self.inference.run(
            query,
            include_bm25_retrieval=False, 
            give_score=True, 
            format_retrieved_docs_function=AvailableService.format_retrieved_docs_function
        )

        # Assertions to verify that the response and sources are valid
        assert isinstance(response, str), "The response should be a string"
        assert isinstance(sources, list), "The sources should be a list"
        assert len(sources) > 0, "There should be at least one source retrieved"
        assert "AI" in response, "The response should mention AI"

    def test_inference_pipeline_custom_format_function(self):
        # Define the query for the test
        query = "What is the importance of quantum computing?"

        # Define a custom formatting function
        def custom_format_function(docs):
            return f"Custom Format: {docs}"

        # Run the inference pipeline with a custom formatting function
        response, sources = self.inference.run(
            query, 
            include_bm25_retrieval=True, 
            give_score=False, 
            format_retrieved_docs_function=custom_format_function
        )

        # Assertions to verify that the response and sources are valid and custom formatted
        assert isinstance(response, str), "The response should be a string"
        assert isinstance(sources, list), "The sources should be a list"
        assert len(sources) > 0, "There should be at least one source retrieved"
        assert "Custom Format" in response, "The response should contain the custom formatted output"

