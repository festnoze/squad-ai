import os
from ragas import evaluate

# new imports
import random
#
from langchain_core.runnables import Runnable
#
from application.retrieved_docs_formating_service import RetrievedDocsService
from common_tools.helpers.llm_helper import Llm
from common_tools.models.embedding_model import EmbeddingModel
from common_tools.helpers.env_helper import EnvHelper
from common_tools.RAG.rag_service import RagService, RagServiceFactory 
from common_tools.RAG.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
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

class RagasService:    
    # region Creation of dataset for evaluation

    async def build_a_sample_dataset_from_trainings_objs_file_and_RAG_inference_execution_async(samples_count:int = 10) -> list[dict]:
        ragas_token = EnvHelper.get_env_variable_value_by_name('RAGAS_APP_TOKEN')
        os.environ['RAGAS_APP_TOKEN'] = ragas_token
        
        metadata_descriptions_for_studi_public_site = MetadataDescriptionHelper.get_metadata_descriptions_for_studi_public_site(AvailableService.out_dir)
        rag_service: RagService = RagServiceFactory.build_from_env_config()
        inference_pipeline = RagInferencePipeline(
                                rag= rag_service,
                                default_filters= StudiPublicWebsiteRagSpecificConfig.get_domain_specific_default_filters(),
                                metadata_descriptions= metadata_descriptions_for_studi_public_site,
                                tools= None)
        
        dataset: list = await RagasService.generate_ground_truth_dataset_from_trainings_objs_file(rag_service.llm_1)
        subset = random.sample(dataset, samples_count) if samples_count else dataset

        for data in subset:
            query = data['user_input']

            analysed_query, retrieved_docs = await inference_pipeline.run_pipeline_dynamic_but_augmented_generation_async(
                query=query,
                include_bm25_retrieval=True,
                give_score=True,
                pipeline_config_file_path = 'studi_com_chatbot_rag_pipeline_default_config_wo_AG_for_streaming.yaml',
                format_retrieved_docs_function=RetrievedDocsService.format_retrieved_docs_function
            )
            data['retrieved_contexts'] = [retrieved_doc.page_content for retrieved_doc in retrieved_docs[0]] #TODO: why retrieved_chunks is an array of array?

            all_chunks_output = []
            AugmentedGenerationFunction = inference_pipeline.workflow_concrete_classes['RAGAugmentedGeneration'].rag_augmented_answer_generation_streaming_async
            async for chunk in AugmentedGenerationFunction(rag_service, query, retrieved_docs[0], analysed_query, function_for_specific_formating_retrieved_docs = RetrievedDocsService.format_retrieved_docs_function):
                all_chunks_output.append(chunk)

            data['response'] = ''.join(all_chunks_output)

        return subset

    async def generate_test_dataset_from_documents_langchain_async(docs: list, generator_llm: Runnable = None, generator_embeddings: EmbeddingModel = None, files_path:str = './outputs', samples_count:int = 10):
        from ragas.testset import TestsetGenerator
        #
        rag_service: RagService = RagServiceFactory.build_from_env_config()
        generator_llm = rag_service.llm_1 if not generator_llm else generator_llm
        generator_embeddings = rag_service.embedding if not generator_embeddings else generator_embeddings
        
        generator = TestsetGenerator(llm=generator_llm, embedding_model=generator_embeddings)

        # Manually extract a subset out of the documents of the same size
        docs_sample = random.sample(docs, samples_count) if samples_count else docs
        dataset = generator.generate_with_langchain_docs(docs_sample, testset_size=samples_count)
        return dataset
    
    async def generate_ground_truth_dataset_from_trainings_objs_file(llm, path:str = './outputs'):
        trainings_objects = await SummaryAndQuestionsChunksService.build_trainings_objects_with_summaries_and_chunks_by_questions_async(path, llm)
        
        # Build the ground truth dataset
        dataset = []
        for training_obj in trainings_objects:
            for chunk in training_obj.doc_chunks:
                for question in chunk.questions:
                    dataset.append({
                            'user_input': question.text,
                            'reference': chunk.text,
                        })
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
    # endregion

    # region Running RAGAS Evaluation
    def run_ragas_evaluation(llm_or_chain: Runnable, dataset: list[dict]):
        evaluation_dataset = EvaluationDataset.from_list(dataset)
        evaluator_llm = LangchainLLMWrapper(llm_or_chain)
        result = evaluate(
                    dataset=evaluation_dataset,
                    metrics=[LLMContextRecall(), Faithfulness(), FactualCorrectness(), ContextPrecision()],
                    llm=evaluator_llm,
                )
        link = result.upload()
        return result
    # endregion