from collections import defaultdict
import os
from dotenv import load_dotenv
import nest_asyncio
import pandas as panda

from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.embedding import EmbeddingModel
from common_tools.models.llm_info import LlmInfo
from common_tools.helpers.execute_helper import Execute
from common_tools.rag.rag_injection_pipeline.rag_injection_pipeline import RagInjectionPipeline
from common_tools.models.llm_info import LlmInfo
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.rag.rag_service import RagService
from common_tools.langchains.langsmith_client import Langsmith

from langchain_community.document_loaders import DirectoryLoader
from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document
from langchain.indexes import VectorstoreIndexCreator
from langchain.chains import RetrievalQA
from langchain_openai import ChatOpenAI
from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
import openai

from langchain.smith import RunEvalConfig
from ragas.testset.synthesizers.generate import TestsetGenerator
from ragas.testset.synthesizers.abstract_query import AbstractQuerySynthesizer, ComparativeAbstractQuerySynthesizer
from ragas.testset.synthesizers.specific_query import SpecificQuerySynthesizer
from ragas.llms.base import LangchainLLMWrapper
from ragas.embeddings.base import LangchainEmbeddingsWrapper
from ragas.testset import Testset
from ragas.testset.transforms import EmbeddingExtractor, KeyphrasesExtractor, TitleExtractor
from ragas.integrations.langchain import EvaluatorChain
from ragas.metrics import (
    answer_correctness,
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
    # context_entity_recall,
    # answer_similarity,
    #ALL_METRICS
)

class RagasService:    
    @staticmethod
    async def generate_ground_truth_async(llm_info: LlmInfo, langchain_documents: list[Document], test_size: int = 2):  
        load_dotenv()
        openai_api_key = os.getenv("OPEN_API_KEY")        
        openai.api_key = openai_api_key
        os.environ["OPENAI_API_KEY"] = openai_api_key

        # from datasets import load_dataset
        # ragas_data = load_dataset("aurelio-ai/ai-arxiv2-ragas-mixtral", split="train")
        # print(ragas_data[0])

        rag_service = RagService(llm_info, EmbeddingModel.OpenAI_TextEmbedding3Small)
        evaluator_llm = rag_service.llm #LangchainLLMWrapper(rag_service.llm)
        evaluator_embedding = rag_service.embedding #LangchainEmbeddingsWrapper(rag_service.embedding)

        docs = [doc for doc in rag_service.langchain_documents if doc.metadata.get("type") == "formation"][:10]
        # text_splitter = RecursiveCharacterTextSplitter(
        #     chunk_size = 1000,
        #     chunk_overlap = 200
        # )
        # chunks = text_splitter.split_documents(docs)
        
        # # works with those docs: 
        # from langchain.document_loaders import DirectoryLoader
        # from common_tools.helpers.file_helper import file
        # docs = []
        # path = "C:/Dev/samples/Sample_Docs_Markdown"
        # files_paths = file.get_files_paths_and_contents(path, 'md')
        # for file_path in files_paths:
        #     file_name = file_path.split('/')[-1].split('.')[0]
        #     content = file.get_as_str(file_path)
        #     doc = Document(page_content=content, metadata={"source": file_name})
        #     docs.append(doc)

        # try:
        #     embedding_extractor = EmbeddingExtractor(embedding_model=rag_service.embedding)
        #     langchain_documents_with_embeddings = await embedding_extractor.transform(chunks[:test_size])

        #     keyphrases_extractor = KeyphrasesExtractor(llm=rag_service.llm)
        #     langchain_documents_with_keyphrases = await keyphrases_extractor.transform(langchain_documents_with_embeddings)

        #     title_extractor = TitleExtractor(llm=rag_service.llm)
        #     langchain_documents_final = await title_extractor.transform(langchain_documents_with_keyphrases)

        # except Exception as e:
        #     print(f"Error applying transformations: {e}")
        
        distributions= [
            (AbstractQuerySynthesizer(llm=evaluator_llm), 0.5),
            (ComparativeAbstractQuerySynthesizer(llm=evaluator_llm), 0.25),
            (SpecificQuerySynthesizer(llm=evaluator_llm), 0.25),
        ]
        generator = TestsetGenerator.from_langchain(llm=evaluator_llm)
        dataset = generator.generate_with_langchain_docs(docs, testset_size=10, transforms_embedding_model=evaluator_embedding, query_distribution=distributions)
        #dataset = generator.generate_with_langchain_docs(chunks[:test_size], testset_size=test_size, transforms_embedding_model=evaluator_embedding)
        #dataset = generator.generate_with_langchain_docs(langchain_documents_final[:test_size], testset_size=test_size, transforms_llm=evaluator_llm, transforms_embedding_model=evaluator_embedding, query_distribution=distributions)
        ds = dataset.to_pandas()
        print(ds)


    @staticmethod
    def generate_ground_truth_from_ragas_site(llm_info: LlmInfo, langchain_documents: list[Document], test_size: int = 2): 
        from ragas.llms import LangchainLLMWrapper        
        load_dotenv()
        nest_asyncio.apply()        
        openai_api_key = os.getenv("OPEN_API_KEY")        
        openai.api_key = openai_api_key
        os.environ["OPENAI_API_KEY"] = openai_api_key

        rag_service = RagService(llm_info, EmbeddingModel.OpenAI_TextEmbedding3Small)
        generator_llm = LangchainLLMWrapper(rag_service.llm)
        generator_embeddings = rag_service.embedding
        generator = TestsetGenerator(llm=generator_llm)
        dataset = generator.generate_with_langchain_docs(langchain_documents[:5], testset_size=test_size)
        dataset.to_pandas()

    @staticmethod
    def generate_ground_truth_notebook1(llm_info: LlmInfo, langchain_documents: list[Document], test_size: int = 2):     
        # try from notebook tuto: https://github.com/langchain-ai/langsmith-cookbook/blob/main/testing-examples/ragas/ragas.ipynb
        load_dotenv()
        openai_api_key = os.getenv("OPEN_API_KEY")        
        openai.api_key = openai_api_key
        os.environ["OPENAI_API_KEY"] = openai_api_key

        loader = TextLoader("./test.txt")
        rag_service = RagService(llm_info, EmbeddingModel.OpenAI_TextEmbedding3Small) #EmbeddingModel.Ollama_AllMiniLM
        injection_pipeline = RagInjectionPipeline(rag_service)
        docs = loader.load_and_split(RecursiveCharacterTextSplitter(
            separators=["\n"],
            chunk_size=200,
            chunk_overlap=20,
            length_function=len
        ))

        langsmith = Langsmith()
        client = langsmith.client
        dataset_url = "https://smith.langchain.com/o/c05186c1-666d-5eac-bbce-5c9c4785bfb1/datasets/e8113156-5c94-4d65-9ee7-f307114d1009?tab=2&paginationState=%7B%22pageIndex%22%3A0%2C%22pageSize%22%3A10%7D"
        dataset_name = os.getenv("LANGCHAIN_PROJECT")
        if not client.has_dataset(dataset_name=dataset_name):
            client.create_dataset(dataset_name)


        # Wrap the RAGAS metrics to use in LangChain
        evaluators = [
            EvaluatorChain(metric)
            for metric in [
                    faithfulness,
                    answer_relevancy,
                    context_precision,
                    context_recall,
                    answer_correctness,
            ]
        ]
        eval_config = RunEvalConfig(custom_evaluators=evaluators)

        results = client.run_on_dataset(
            dataset_name=dataset_name,
            llm_or_chain_factory=rag_service.llm,
            evaluation=eval_config,
        )

        df_results = panda.DataFrame.from_dict(results)
        print(df_results)
        
        retriever = rag_service.vectorstore.as_retriever()

        # path = "outputs/all/"
        # loader = DirectoryLoader(path, glob="**/*.json")
        # docs = loader.load()
        
        
        # 
        # os.environ["OPENAI_API_KEY"] = os.getenv("OPEN_API_KEY") # needed by ragas which use GPT-4o-mini
        
        # evaluator_llm = LangChainFactory.create_llm_from_info(llm_info) #AvailableService.rag_service.llm)
        # embedding = EmbeddingModel.OpenAI_TextEmbedding3Small.create_instance()
        
        # generator = TestsetGenerator(
        #     LangchainLLMWrapper(evaluator_llm),
        #     #embedding
        # )

        # testset = generator.generate_with_langchain_docs(docs, testset_size=5)

        # testset = testset.to_pandas()
        # print(testset)


    @staticmethod
    def generate_ground_truth2(llm_info: LlmInfo, langchain_documents: list[Document], test_size: int = 2):
        nest_asyncio.apply()
        #Execute.activate_global_function_parameters_types_verification()
        os.environ["OPENAI_API_KEY"] = os.getenv("OPEN_API_KEY") # needed by ragas which use GPT-4o-mini
        
        evaluator_llm = LangChainFactory.create_llm_from_info(llm_info) #AvailableService.rag_service.llm)
        embedding = EmbeddingModel.OpenAI_TextEmbedding3Small.create_instance()
        
        generator = TestsetGenerator.from_langchain(
            LangchainLLMWrapper(evaluator_llm),
            #embedding
        )
        
        distributions= [
            (AbstractQuerySynthesizer(llm=evaluator_llm), 0.25),
            (ComparativeAbstractQuerySynthesizer(llm=evaluator_llm), 0.25),
            (SpecificQuerySynthesizer(llm=evaluator_llm), 0.5),
        ]

        docs = langchain_documents#[200:]
        docs_sample = RagasService.get_documents_samples_by_metadata_values(docs, test_size, sample_by_distinct_metadata_name='type', sample_by_distinct_metadata_value='formation')
        testset = generator.generate_with_langchain_docs(docs_sample, test_size)

        test_df = testset.to_pandas()
        print(test_df)

    @staticmethod
    def get_documents_samples_by_metadata_values(documents: list[Document], sample_count: int, sample_by_distinct_metadata_name: str = None, sample_by_distinct_metadata_value: str = None) -> list[Document]:
        documents_by_type = defaultdict(list)
        if sample_by_distinct_metadata_name:
            for document in documents:
                doc_filter_metadata_value = document.metadata.get(sample_by_distinct_metadata_name)
                if doc_filter_metadata_value and len(documents_by_type[doc_filter_metadata_value]) < sample_count:
                    if not sample_by_distinct_metadata_value or doc_filter_metadata_value == sample_by_distinct_metadata_value:
                        documents_by_type[doc_filter_metadata_value].append(document)
        else:
            for i, document in enumerate(documents[:sample_count]):
                documents_by_type[i].append(document)

        result = [doc for docs in documents_by_type.values() for doc in docs]
        return result