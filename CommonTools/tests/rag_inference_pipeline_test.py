from unittest.mock import MagicMock, patch
from common_tools.RAG.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
from rag_inference_pipeline_fakes import RAGGuardrailsFake, RAGPreTreatmentFake, RAGHybridRetrievalFake, RAGAugmentedGenerationFake, RAGPostTreatmentFake

class Test_RAGInferencePipeline:

    def setup_method(self):
        self.mock_rag_service = MagicMock()

        # Define any methods of the ragService which are expected to be called
        self.mock_rag_service.retrieve.return_value = "RAG Task Result"

        # Create fake classes to override the actual workflow classes
        self.override_workflow_available_classes = {
            'RAGGuardrails': RAGGuardrailsFake,
            'RAGPreTreatment': RAGPreTreatmentFake,
            'RAGHybridRetrieval': RAGHybridRetrievalFake,
            'RAGAugmentedGeneration': RAGAugmentedGenerationFake,
            'RAGPostTreatment': RAGPostTreatmentFake
        }

        # Instantiate the RAGInferencePipeline with the mock service
        self.rag_pipeline = RagInferencePipeline(rag=self.mock_rag_service)

    def test_run_with_default_config(self):
        query = "What is the capital of France?"
        results = self.rag_pipeline.run(query, override_workflow_available_classes=self.override_workflow_available_classes)

        # Verify that the results match the expected fake outputs
        assert results == (
            [("Guardrails Result", {"query": query})],
            [('Post-Treatment Result', {'post_processed': True})]
        )

    def test_run_with_bm25_retrieval_disabled(self):
        query = "Tell me about the Eiffel Tower."
        results = self.rag_pipeline.run(query, include_bm25_retrieval=False, override_workflow_available_classes=self.override_workflow_available_classes)

        assert results == (
            [("Guardrails Result", {"query": query})],
            [('Post-Treatment Result', {'post_processed': True})]
        )
    
    def test_run_with_custom_post_processing_function(self):
        query = "What is AI?"
        
        def custom_format_function(docs):
            return f"Formatted: {docs}"

        results = self.rag_pipeline.run(
            query,
            format_retrieved_docs_function=custom_format_function,
            override_workflow_available_classes=self.override_workflow_available_classes
        )

        # Verify that the custom format function is applied
        assert results == (
            [("Guardrails Result", {"query": query})],
            [('Post-Treatment Result', {'post_processed': True})]
        )
