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
from pandas import DataFrame
from common_tools.helpers.execute_helper import Execute

class RagasService:
    @staticmethod
    def generate_ground_truth(llm_info: LlmInfo, langchain_documents: list[Document], test_size: int = 2):
        
        from langchain_community.document_loaders import TextLoader
        from langchain.indexes import VectorstoreIndexCreator
        from langchain.chains import RetrievalQA
        from langchain_openai import ChatOpenAI
        
        nest_asyncio.apply()
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
        loader = TextLoader("./test.txt")
        docs = loader.load_and_split()
        os.environ["OPENAI_API_KEY"] = os.getenv("OPEN_API_KEY") # needed by ragas which use GPT-4o-mini
        
        evaluator_llm = LangChainFactory.create_llm_from_info(llm_info) #AvailableService.rag_service.llm)
        embedding = EmbeddingModel.OpenAI_TextEmbedding3Small.create_instance()
        
        generator = TestsetGenerator.from_langchain(
            LangchainLLMWrapper(evaluator_llm),
            #embedding
        )

        testset = generator.generate_with_langchain_docs(docs, test_size)

        test_df = testset.to_pandas()
        print(test_df)


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