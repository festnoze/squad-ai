import random
from fastapi import APIRouter
from common_tools.helpers.env_helper import EnvHelper
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.embedding_model import EmbeddingModel
from common_tools.models.embedding_model_factory import EmbeddingModelFactory
from vector_database_creation.summary_and_questions_chunks_service import SummaryAndQuestionsChunksService

evaluation_router = APIRouter(prefix="/rag/evaluation", tags=["Evaluation"])

@evaluation_router.post("/groundtruth/generate")
async def generate_ground_truth():
    from application.ragas_service import RagasService
    #
    path:str = './outputs'
    llms_infos = EnvHelper.get_llms_infos_from_env_config()
    llms = LangChainFactory.create_llms_from_infos(llms_infos)
    embedding_model = EnvHelper.get_embedding_model()
    EmbeddingModelFactory.create_instance(embedding_model)
    #
    trainings_docs_with_summary_chunked_by_questions = await SummaryAndQuestionsChunksService.build_trainings_objects_with_summaries_and_chunks_by_questions_from_docs_async(path, None, llms)
    trainings_samples_count = 5
    #trainings_samples = random.sample(trainings_docs, trainings_samples_count) if trainings_samples_count else trainings_docs

    # Works:
    testset = await RagasService.build_sample_inference_dataset_async(samples_count= trainings_samples_count)
    eval_res = RagasService.run_ragas_evaluation(llms[0], testset)
    return {"testset": testset}

    testset = await RagasService.generate_test_dataset_from_documents_langchain_async(
                                    trainings_docs_with_summary_chunked_by_questions,
                                    llms[0], 
                                    embedding_model, 
                                    samples_count= trainings_samples_count)
    RagasService.run_ragas_evaluation(llms[0], testset)

    knowledge_graph = RagasService.generate_or_load_ragas_knowledge_graph_from_documents(
                                    trainings_docs_with_summary_chunked_by_questions,
                                    llms[0], 
                                    embedding_model, 
                                    samples_count= trainings_samples_count)
    
    testset = RagasService.run_evals_from_knowledge_graph(knowledge_graph, llms[0], embedding_model, trainings_samples_count)
    
    return {"testset": testset.to_dict()}