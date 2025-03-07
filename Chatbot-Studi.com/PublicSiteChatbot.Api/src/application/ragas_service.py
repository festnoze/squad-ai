# from collections import defaultdict
# import os
# from dotenv import load_dotenv
# import nest_asyncio
# import pandas as panda
# import openai

# from common_tools.langchains.langchain_factory import LangChainFactory
# from common_tools.models.embedding_model import EmbeddingModel
# from common_tools.models.embedding_type import EmbeddingType
# from common_tools.models.embedding_model_factory import EmbeddingModelFactory
# from common_tools.models.llm_info import LlmInfo
# from common_tools.helpers.execute_helper import Execute
# from common_tools.rag.rag_ingestion_pipeline.rag_ingestion_pipeline import RagIngestionPipeline
# from common_tools.models.langchain_adapter_type import LangChainAdapterType
# from common_tools.langchains.langsmith_client import Langsmith
# from common_tools.langchains.langchain_factory import LangChainFactory
# from common_tools.helpers.env_helper import EnvHelper

# from langchain_community.document_loaders import DirectoryLoader
# from langchain_community.document_loaders import TextLoader
# from langchain_core.documents import Document
# from langchain.indexes import VectorstoreIndexCreator
# from langchain.chains import RetrievalQA
# from langchain_openai import ChatOpenAI
# from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
# from langchain.smith import RunEvalConfig

# from ragas.testset.synthesizers.generate import TestsetGenerator
# from ragas.llms.base import LangchainLLMWrapper
# from ragas.embeddings.base import LangchainEmbeddingsWrapper
# from ragas.testset import Testset
# from ragas.testset.transforms import EmbeddingExtractor, KeyphrasesExtractor, TitleExtractor
# from ragas.integrations.langchain import EvaluatorChain
# from ragas.metrics import LLMContextRecall, Faithfulness, FactualCorrectness, SemanticSimilarity
# #from ragas.testset.synthesizers import AbstractQuerySynthesizer, ComparativeAbstractQuerySynthesizer, SpecificQuerySynthesizer
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
from application.studi_public_website_metadata_descriptions import MetadataDescriptionHelper
from application.available_service import AvailableService
from application.studi_public_website_rag_specific_config import StudiPublicWebsiteRagSpecificConfig
from vector_database_creation.summary_chunks_with_questions_documents import SummaryWithQuestionsByChunkDocumentsService
#
from ragas import EvaluationDataset
from ragas import evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import LLMContextRecall, Faithfulness, FactualCorrectness

class RagasService:    
    async def run_eval_on_ground_truth_dataset_async(llm_or_chain: Runnable, samples_count:int = 10):
        ragas_token = EnvHelper.generic_get_env_variable_value_by_name('RAGAS_APP_TOKEN')
        os.environ['RAGAS_APP_TOKEN'] = ragas_token
        
        metadata_descriptions_for_studi_public_site = MetadataDescriptionHelper.get_metadata_descriptions_for_studi_public_site(AvailableService.out_dir)
        rag_service: RagService = RagServiceFactory.build_from_env_config()
        inference_pipeline = RagInferencePipeline(
                                rag= rag_service,
                                default_filters= StudiPublicWebsiteRagSpecificConfig.get_domain_specific_default_filters(),
                                metadata_descriptions= metadata_descriptions_for_studi_public_site,
                                tools= None)
        
        dataset: list = await RagasService.get_ground_truth_dataset_async()
        subset = random.sample(dataset, samples_count) if samples_count else dataset

        for data in subset:
            query = data['user_input']
            analysed_query, retrieved_docs = await inference_pipeline.run_pipeline_dynamic_but_augmented_generation_async(
                query=query,
                include_bm25_retrieval=True,
                give_score=True,
                pipeline_config_file_path = 'studi_com_chatbot_rag_pipeline_default_config_wo_AG_for_streaming.yaml',
                format_retrieved_docs_function=AvailableService.format_retrieved_docs_function)
            data['retrieved_contexts'] = [retrieved_doc.page_content for retrieved_doc in retrieved_docs[0]] #TODO: why retrieved_chunks is an array of array?

            all_chunks_output = []
            augmented_generation_function = inference_pipeline.workflow_concrete_classes['RAGAugmentedGeneration'].rag_augmented_answer_generation_streaming_async
            async for chunk in augmented_generation_function(llm_or_chain, query, retrieved_docs[0], analysed_query, AvailableService.format_retrieved_docs_function):
                all_chunks_output.append(chunk)

            data['response'] = ''.join(all_chunks_output)

        evaluation_dataset = EvaluationDataset.from_list(subset)
        evaluator_llm = LangchainLLMWrapper(llm_or_chain)
        result = evaluate(
                    dataset=evaluation_dataset,
                    metrics=[LLMContextRecall(), Faithfulness(), FactualCorrectness()],
                    llm=evaluator_llm,
                )
        link = result.upload()
        return result
    
    async def get_ground_truth_dataset_async(files_path:str = './outputs'):
        trainings_objects = await RagasService.get_trainings_objects_or_docs_async(files_path)
        
        # Build the ground truth dataset
        dataset = []
        for training_obj in trainings_objects:
            for chunk in training_obj.doc_chunks:
                for question in chunk.questions:
                    dataset.append(
                        {
                            'user_input': question.text,
                            'reference': chunk.text,
                            'reference_full': training_obj.doc_summary, #training_obj.doc_content,
                            'reference_id': training_obj.metadata['id'],
                            'reference_type': training_obj.metadata['type'],
                            'reference_name': training_obj.metadata['name'],
                        }
                    )
        return dataset

    async def get_trainings_objects_or_docs_async(files_path, return_trainings_docs=False):
        summaries_and_questions_generation_service = SummaryWithQuestionsByChunkDocumentsService()
        trainings_docs = summaries_and_questions_generation_service.build_trainings_docs(files_path, False, True)
        trainings_objects = await summaries_and_questions_generation_service.build_trainings_objects_with_summaries_and_chunks_by_questions_async(files_path, trainings_docs)
        
        if return_trainings_docs:
            #TODO: see if it worth the same than the previous trainings_docs above
            trainings_docs = summaries_and_questions_generation_service.build_trainings_docs_from_objs(False, trainings_objects)
            return trainings_docs
        else:
            return trainings_objects
        

    def generate_test_dataset_from_documents_generic(docs: list, generator_llm: Runnable, generator_embedding: EmbeddingModel, samples_count:int = 10, saved_knowledge_graph_file_path = './outputs/ragas_kg.json'):
        from ragas.testset.graph import KnowledgeGraph
        from ragas.testset.graph import Node, NodeType
        from ragas.testset.transforms import default_transforms, apply_transforms
        from ragas.testset import TestsetGenerator
        from ragas.testset.synthesizers import default_query_distribution, SingleHopSpecificQuerySynthesizer, MultiHopAbstractQuerySynthesizer, MultiHopSpecificQuerySynthesizer
        #
        
        if file.exists(saved_knowledge_graph_file_path):
            ragas_kg = KnowledgeGraph.load(saved_knowledge_graph_file_path)
        else:
            kg = KnowledgeGraph()
            for doc in docs:
                kg.nodes.append(
                    Node(
                        type=NodeType.DOCUMENT,
                        properties={"page_content": doc.page_content, "document_metadata": doc.metadata}
                    )
                )

            default_transforms = default_transforms(documents=docs, llm=generator_llm, embedding_model=generator_embedding)
            apply_transforms(kg, default_transforms)

            # Save RAGAS knowledge graph
            kg.save(saved_knowledge_graph_file_path)

        # Run evaluations on the generated testset
        generator = TestsetGenerator(llm=generator_llm, embedding_model=generator_embedding, knowledge_graph=ragas_kg)

        query_distribution = [
                (SingleHopSpecificQuerySynthesizer(llm=generator_llm), 0.5),
                (MultiHopAbstractQuerySynthesizer(llm=generator_llm), 0.25),
                (MultiHopSpecificQuerySynthesizer(llm=generator_llm), 0.25),
        ]
        testset = generator.generate(testset_size=samples_count, query_distribution=query_distribution)
        #testset.to_pandas()
        return testset
    
    async def generate_test_dataset_from_documents_langchain_async(docs: list, generator_llm: Runnable = None, generator_embeddings: EmbeddingModel = None, files_path:str = './outputs', samples_count:int = 10):
        from ragas.testset import TestsetGenerator
        #
        rag_service: RagService = RagServiceFactory.build_from_env_config()
        generator_llm = rag_service.llm_1 if not generator_llm else generator_llm
        generator_embeddings = rag_service.embedding if not generator_embeddings else generator_embeddings
        
        generator = TestsetGenerator(llm=generator_llm, embedding_model=generator_embeddings)
        dataset = generator.generate_with_langchain_docs(docs, testset_size=samples_count)
        #dataset.to_pandas()
        return dataset


        
        