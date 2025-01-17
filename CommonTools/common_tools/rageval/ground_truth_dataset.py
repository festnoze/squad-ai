from common_tools.helpers.txt_helper import txt
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.embedding_type import EmbeddingModel
from common_tools.models.llm_info import LlmInfo
from langchain_core.documents import Document
from ragas.testset.synthesizers.generate import TestsetGenerator
from ragas.testset.synthesizers.abstract_query import AbstractQuerySynthesizer, ComparativeAbstractQuerySynthesizer
from ragas.testset.synthesizers.specific_query import SpecificQuerySynthesizer
from pandas import DataFrame

class GroundTruthDataset:
    def __init__(self, documents:list[Document], generator_llm_info: LlmInfo, critic_llm_info: LlmInfo, embedding_info: EmbeddingModel, distributions: dict = None, test_size: int = 10):
        embedding = embedding_info.create_instance()

        self.generator = TestsetGenerator.from_langchain(
            LangChainFactory.create_llm_from_info(generator_llm_info),
            LangChainFactory.create_llm_from_info(critic_llm_info),
            embedding
        )

        if not distributions:
            distributions= [
                (AbstractQuerySynthesizer(llm=generator_llm_info), 0.25),
                (ComparativeAbstractQuerySynthesizer(llm=generator_llm_info), 0.25),
                (SpecificQuerySynthesizer(llm=generator_llm_info), 0.5),
            ]

        testset = self.generator.generate_with_langchain_docs(documents, test_size, distributions)

        test_df = testset.to_pandas() 
        txt.print(test_df)