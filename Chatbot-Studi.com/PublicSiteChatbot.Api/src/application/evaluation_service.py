import os
from ragas import evaluate

# new imports
import random
#
from langchain_core.runnables import Runnable
#
from common_tools.helpers.llm_helper import Llm
from common_tools.models.embedding_model import EmbeddingModel
from common_tools.helpers.env_helper import EnvHelper
from common_tools.rag.rag_service import RagService
from common_tools.rag.rag_service_factory import RagServiceFactory
from common_tools.rag.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
from common_tools.helpers.file_helper import file
#
from application.studi_public_website_metadata_descriptions import MetadataDescriptionHelper
from application.available_service import AvailableService
from application.studi_public_website_rag_specific_config import StudiPublicWebsiteRagSpecificConfig
from vector_database_creation.summary_and_questions_chunks_service import SummaryAndQuestionsChunksService
#
from ragas import EvaluationDataset
from ragas import evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import LLMContextRecall, Faithfulness, FactualCorrectness, ContextPrecision, ContextRelevance, AnswerAccuracy
from ragas.testset.graph import KnowledgeGraph
from ragas.testset.graph import Node, NodeType
from ragas.testset.transforms import default_transforms, apply_transforms
from ragas.testset import TestsetGenerator
from ragas.testset.synthesizers import default_query_distribution, SingleHopSpecificQuerySynthesizer, MultiHopAbstractQuerySynthesizer, MultiHopSpecificQuerySynthesizer

class EvaluationService:
    rag_service: RagService = RagServiceFactory.build_from_env_config()

    @staticmethod
    async def create_q_and_a_sample_dataset_from_existing_summary_and_questions_objects_async(samples_count: int = 0, categorize_by_metadata: bool = False, input_objects_file_path:str = './outputs'):
        trainings_objects = await SummaryAndQuestionsChunksService.build_trainings_objects_with_summaries_and_chunks_by_questions_async(input_objects_file_path, EvaluationService.rag_service.llm_1)
        
        # Build the Q&A 'ground truth' dataset
        dataset = []
        for training_obj in trainings_objects:
            for chunk in training_obj.doc_chunks:
                for question in chunk.questions:
                    dataset.append({
                            'user_input': question.text,
                            'reference': chunk.text,
                        })
                    
        # If samples_count is provided, randomly sample from the dataset
        subset = random.sample(dataset, samples_count) if samples_count and samples_count > 0 else dataset
        return subset
    
    @staticmethod
    async def add_to_dataset_retrieved_chunks_and_augmented_generation_from_RAG_inference_execution_async(dataset :list) -> list[dict]:
        ragas_token = EnvHelper.get_env_variable_value_by_name('RAGAS_APP_TOKEN')
        os.environ['RAGAS_APP_TOKEN'] = ragas_token
        
        metadata_descriptions_for_studi_public_site = MetadataDescriptionHelper.get_metadata_descriptions_for_studi_public_site(AvailableService.out_dir)
        rag_service: RagService = RagServiceFactory.build_from_env_config()
        inference_pipeline = RagInferencePipeline(
                                rag= rag_service,
                                default_filters= StudiPublicWebsiteRagSpecificConfig.get_domain_specific_default_filters(),
                                metadata_descriptions= metadata_descriptions_for_studi_public_site,
                                tools= None)
        for data in dataset:
            query = data['user_input']

            analysed_query, retrieved_docs = await inference_pipeline.run_pipeline_dynamic_but_augmented_generation_async(
                query=query,
                include_bm25_retrieval=True,
                give_score=True,
                pipeline_config_file_path = 'studi_com_chatbot_rag_pipeline_default_config_wo_AG_for_streaming.yaml',
                format_retrieved_docs_function=AvailableService.format_retrieved_docs_function
            )
            data['retrieved_contexts'] = [retrieved_doc.page_content for retrieved_doc in retrieved_docs[0]] #TODO: why retrieved_chunks is an array of array?

            all_chunks_output = []
            AugmentedGenerationFunction = inference_pipeline.workflow_concrete_classes['RAGAugmentedGeneration'].rag_augmented_answer_generation_streaming_async
            async for chunk in AugmentedGenerationFunction(rag_service, query, retrieved_docs[0], analysed_query, function_for_specific_formating_retrieved_docs = AvailableService.format_retrieved_docs_function):
                all_chunks_output.append(chunk)

            data['response'] = ''.join(all_chunks_output)

        return dataset

    @staticmethod
    async def generate_test_dataset_from_documents_langchain_async(lc_docs: list, generator_llm: Runnable = None, generator_embeddings: EmbeddingModel = None, samples_count:int = 10):
        from ragas.testset import TestsetGenerator
        #
        rag_service: RagService = RagServiceFactory.build_from_env_config()
        generator_llm = rag_service.llm_1 if not generator_llm else generator_llm
        generator_embeddings = rag_service.embedding if not generator_embeddings else generator_embeddings
        
        generator = TestsetGenerator(llm=generator_llm, embedding_model=generator_embeddings)

        # Manually extract a subset out of the documents of the same size
        docs_sample = random.sample(lc_docs, samples_count) if samples_count else lc_docs
        dataset = generator.generate_with_langchain_docs(docs_sample, testset_size=samples_count)
        return dataset
    
    def generate_or_load_ragas_knowledge_graph_from_documents(docs: list, generator_llm: Runnable, generator_embedding: EmbeddingModel, samples_count:int = 10, saved_knowledge_graph_file_path = './outputs/ragas_kg.json'):
        if file.exists(saved_knowledge_graph_file_path):
            ragas_kg = KnowledgeGraph.load(saved_knowledge_graph_file_path)
        else:
            ragas_kg = KnowledgeGraph()
            for doc in docs:
                ragas_kg.nodes.append(
                    Node(
                        type=NodeType.DOCUMENT,
                        properties={"page_content": doc.page_content, "document_metadata": doc.metadata}
                    )
                )

            transforms = default_transforms(documents=docs, llm=generator_llm, embedding_model=generator_embedding)
            apply_transforms(ragas_kg, transforms)

            # Save RAGAS knowledge graph
            ragas_kg.save(saved_knowledge_graph_file_path)
        return ragas_kg

    def generate_tests_from_knowledge_graph(ragas_kg: KnowledgeGraph, generator_llm: Runnable, generator_embedding: EmbeddingModel, samples_count:int = 10):
        # Run evaluations on the generated testset
        generator = TestsetGenerator(llm=generator_llm, embedding_model=generator_embedding, knowledge_graph=ragas_kg)

        query_distribution = [
                (SingleHopSpecificQuerySynthesizer(llm=generator_llm), 1.0),
                # (MultiHopAbstractQuerySynthesizer(llm=generator_llm), 0.25),
                # (MultiHopSpecificQuerySynthesizer(llm=generator_llm), 0.25),
        ]
        testset = generator.generate(testset_size=samples_count, query_distribution=query_distribution)
        return testset
    
    async def run_ragas_evaluation_and_upload_async(dataset: list[dict]):
        evaluation_dataset = EvaluationDataset.from_list(dataset)
        evaluator_llm = LangchainLLMWrapper(EvaluationService.rag_service.llm_1)

        result = evaluate(
                    dataset=evaluation_dataset,
                    metrics=[LLMContextRecall(), Faithfulness(), FactualCorrectness(), ContextPrecision()],
                    llm=evaluator_llm,
                )
        link = result.upload()
        return result, link