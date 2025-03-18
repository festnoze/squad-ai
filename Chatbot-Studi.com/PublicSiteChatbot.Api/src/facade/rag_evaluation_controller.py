import random
from fastapi import APIRouter
from common_tools.helpers.env_helper import EnvHelper
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.embedding_model import EmbeddingModel
from common_tools.models.embedding_model_factory import EmbeddingModelFactory

evaluation_router = APIRouter(prefix="/rag/evaluation", tags=["Evaluation"])

@evaluation_router.post("/groundtruth/generate")
async def generate_ground_truth():
    from application.ragas_service import RagasService
    #
    files_path:str = './outputs'
    llms_infos = EnvHelper.get_llms_infos_from_env_config()
    llms = LangChainFactory.create_llms_from_infos(llms_infos)
    embedding_model = EnvHelper.get_embedding_model()
    EmbeddingModelFactory.create_instance(embedding_model)
    trainings_docs = await RagasService.get_trainings_objects_or_docs_async(files_path, True)
    trainings_samples_count = 10
    #trainings_samples = random.sample(trainings_docs, trainings_samples_count) if trainings_samples_count else trainings_docs

    # This one works:  
    testset = await RagasService.run_eval_on_ground_truth_dataset_async(llms[0], samples_count= trainings_samples_count)
    #testset = await RagasService.generate_test_dataset_from_documents_langchain_async(
    # testset = RagasService.generate_or_load_test_dataset_from_documents_generic(
    #                                 trainings_docs,
    #                                 llms[0], 
    #                                 embedding_model, 
    #                                 samples_count= trainings_samples_count)
    return {"testset": testset.to_dict()}
