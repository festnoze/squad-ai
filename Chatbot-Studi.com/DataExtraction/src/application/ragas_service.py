from collections import defaultdict
import os
from dotenv import load_dotenv
import nest_asyncio
import pandas as panda

from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.embedding_model import EmbeddingModel
from common_tools.models.embedding_type import EmbeddingType
from common_tools.models.embedding_model_factory import EmbeddingModelFactory
from common_tools.models.llm_info import LlmInfo
from common_tools.helpers.execute_helper import Execute
from common_tools.rag.rag_ingestion_pipeline.rag_ingestion_pipeline import RagIngestionPipeline
from common_tools.models.llm_info import LlmInfo
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.rag.rag_service import RagService
from common_tools.langchains.langsmith_client import Langsmith
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.helpers.env_helper import EnvHelper

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
from ragas.llms.base import LangchainLLMWrapper
from ragas.embeddings.base import LangchainEmbeddingsWrapper
from ragas.testset import Testset
from ragas.testset.transforms import EmbeddingExtractor, KeyphrasesExtractor, TitleExtractor
from ragas.integrations.langchain import EvaluatorChain
from ragas.metrics import LLMContextRecall, Faithfulness, FactualCorrectness, SemanticSimilarity
#from ragas.testset.synthesizers import AbstractQuerySynthesizer, ComparativeAbstractQuerySynthesizer, SpecificQuerySynthesizer
from ragas import evaluate

from vector_database_creation.generate_summaries_chunks_questions_and_metadata import GenerateDocumentsSummariesChunksQuestionsAndMetadata

class RagasService:    
    def get_ground_truth_dataset(out_dir:str = './outputs', llm_and_fallback: list[LlmInfo] = None):
        summaries_and_questions_generation_service = GenerateDocumentsSummariesChunksQuestionsAndMetadata()
        questions_with_answers = summaries_and_questions_generation_service.load_or_generate_all_docs_from_summaries_and_questions(
                                                path= out_dir,
                                                llm_and_fallback= None,
                                                separate_chunks_and_questions=True)
        return questions_with_answers
