from collections import defaultdict
import os
from dotenv import load_dotenv
import nest_asyncio
import pandas as panda
import openai

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

from vector_database_creation.summary_chunks_with_questions_documents import SummaryWithQuestionsByChunkDocumentsService

class RagasService:    
    async def get_ground_truth_dataset_async(files_path:str = './outputs', llm_and_fallback: list[LlmInfo] = None):
        summaries_and_questions_generation_service = SummaryWithQuestionsByChunkDocumentsService()
        trainings_docs = summaries_and_questions_generation_service.build_trainings_docs(files_path, False, True)
        trainings_objects = await summaries_and_questions_generation_service.build_trainings_objects_with_summaries_and_chunks_by_questions_async(files_path, trainings_docs)
        
        # Build the ground truth dataset
        dataset = []
        for training_obj in trainings_objects:
            for chunk in training_obj.doc_chunks:
                for question in chunk.questions:
                    dataset.append(
                        {
                            'user_input': question.text,
                            'reference': training_obj.doc_summary,
                            'reference_full': training_obj.doc_content,
                            'ref_id': training_obj.metadata['id'],
                            'ref_type': training_obj.metadata['type'],
                            'ref_name': training_obj.metadata['name'],
                        }
                    )
        return dataset

        
