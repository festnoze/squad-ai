from unittest.mock import MagicMock, patch
from common_tools.rag.rag_inference_pipeline.rag_augmented_generation_tasks import RAGAugmentedGeneration
from common_tools.rag.rag_inference_pipeline.rag_guardrails_tasks import RAGGuardrails
from common_tools.rag.rag_inference_pipeline.rag_retrieval import RagRetrieval
from common_tools.rag.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
from common_tools.rag.rag_inference_pipeline.rag_post_treatment_tasks import RAGPostTreatment
from common_tools.rag.rag_inference_pipeline.rag_pre_treatment_tasks import RAGPreTreatment
from common_tools.helpers.test_helper import TestHelper

class Test_RAGInferencePipeline:

    def setup_method(self):
        self.mock_rag_service = MagicMock()

        # Define any methods of the ragService which are expected to be called
        self.mock_rag_service.retrieve.return_value = "rag Task Result"

        self.augmented_answer_generation_method_name = 'rag_augmented_answer_generation_no_streaming_async'
        async def get_encoded_generator_async(*args, **kwargs):
            yield f"Mocked {self.augmented_answer_generation_method_name} called".encode('utf-8')

        # Create fake classes to override the actual workflow classes
        self.override_workflow_available_classes = {
            'RAGGuardrails': TestHelper.create_dynamic_fake_class_of(RAGGuardrails, 'RAGGuardrailsFake'),
            'RAGPreTreatment': TestHelper.create_dynamic_fake_class_of(RAGPreTreatment, 'RAGPreTreatmentFake'),
            'RagRetrieval': TestHelper.create_dynamic_fake_class_of(RagRetrieval, 'RagRetrievalFake'),
            'RAGAugmentedGeneration': TestHelper.create_dynamic_fake_class_of(RAGAugmentedGeneration, 'RAGAugmentedGenerationFake', 
                                    override_methods= { self.augmented_answer_generation_method_name: get_encoded_generator_async } ),
            'RAGPostTreatment': TestHelper.create_dynamic_fake_class_of(RAGPostTreatment, 'RAGPostTreatmentFake')
        }

        # Instantiate the RAGInferencePipeline with the mock service
        self.rag_pipeline = RagInferencePipeline(rag=self.mock_rag_service)

    def test_run_with_default_config(self):
        query = "What is blabla?"
        results = self.rag_pipeline.run_pipeline_dynamic(query, override_workflow_available_classes=self.override_workflow_available_classes)

        assert results == f"Mocked {self.augmented_answer_generation_method_name} called"

    def test_run_with_bm25_retrieval_disabled(self):
        query = "Tell me about blabla."
        results = self.rag_pipeline.run_pipeline_dynamic(query, include_bm25_retrieval=False, override_workflow_available_classes=self.override_workflow_available_classes)

        assert results == f"Mocked {self.augmented_answer_generation_method_name} called"
    
    # def test_run_with_custom_post_processing_function(self):
    #     query = "What is AI?"
        
    #     def custom_format_function(docs):
    #         return f"Formatted: {docs}"

    #     results = self.rag_pipeline.run(
    #         query,
    #         format_retrieved_docs_function=custom_format_function,
    #         override_workflow_available_classes=self.override_workflow_available_classes
    #     )

    #     # Verify that the custom format function is applied
    #     assert results == 'Formatted: Mocked response_post_treatment called'
