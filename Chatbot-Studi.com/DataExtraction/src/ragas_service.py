from collections import defaultdict
import os
import nest_asyncio
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.embedding import EmbeddingModel
from common_tools.models.llm_info import LlmInfo
from langchain_core.documents import Document
from ragas.testset.synthesizers.generate import TestsetGenerator
from ragas.testset.synthesizers.abstract_query import AbstractQuerySynthesizer, ComparativeAbstractQuerySynthesizer
from ragas.testset.synthesizers.specific_query import SpecificQuerySynthesizer
from ragas.llms.base import LangchainLLMWrapper
import pandas as panda
from common_tools.helpers.execute_helper import Execute
from common_tools.rag.rag_injection_pipeline.rag_injection_pipeline import RagInjectionPipeline
from common_tools.models.llm_info import LlmInfo
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.rag.rag_service import RagService


from langchain_community.document_loaders import TextLoader
from langchain.indexes import VectorstoreIndexCreator
from langchain.chains import RetrievalQA
from langchain_openai import ChatOpenAI
from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
import openai

class RagasService:
    @staticmethod
    def generate_ground_truth(llm_info: LlmInfo, langchain_documents: list[Document], test_size: int = 2):     
        # loader = TextLoader("./test.txt")
        # index = VectorstoreIndexCreator(embedding=EmbeddingModel.OpenAI_TextEmbedding3Small.create_instance()).from_loaders([loader])


        # llm = ChatOpenAI(temperature=0)
        # qa_chain = RetrievalQA.from_chain_type(
        #     llm,
        #     retriever=index.vectorstore.as_retriever(),
        #     return_source_documents=True,
        # )
        # question = "Quel est le programme de cette formation ?"
        # result = qa_chain({"query": question})
        # answer = result["result"]
        # print(answer)
        from dotenv import load_dotenv
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

        retriever = rag_service.vectorstore.as_retriever()

        from langchain.smith import RunEvalConfig
        from ragas.integrations.langchain import EvaluatorChain
        from ragas.metrics import (
            answer_correctness,
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        from common_tools.langchains.langsmith_client import Langsmith
        langsmith = Langsmith()
        client = langsmith.client

        dataset_url = "https://smith.langchain.com/o/c05186c1-666d-5eac-bbce-5c9c4785bfb1/datasets/e8113156-5c94-4d65-9ee7-f307114d1009?tab=2&paginationState=%7B%22pageIndex%22%3A0%2C%22pageSize%22%3A10%7D"
        dataset_name = 'drupal_testset_02' #os.getenv("LANGCHAIN_PROJECT")
        if not client.has_dataset(dataset_name=dataset_name):
            client.create_dataset(dataset_name)


        # Wrap the RAGAS metrics to use in LangChain
        evaluators = [
            EvaluatorChain(metric)
            for metric in [
                answer_correctness,
                answer_relevancy,
                context_precision,
                context_recall,
                faithfulness,
            ]
        ]

        nest_asyncio.apply()
        eval_config = RunEvalConfig(custom_evaluators=evaluators)

        results = client.run_on_dataset(
            dataset_name=dataset_name,
            llm_or_chain_factory=rag_service.llm,
            evaluation=eval_config,
        )

        df_results = panda.DataFrame.from_dict(results)
        print(df_results)

        # from langchain_community.document_loaders import DirectoryLoader
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