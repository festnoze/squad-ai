from fastapi import APIRouter
from common_tools.helpers.env_helper import EnvHelper
from common_tools.langchains.langchain_factory import LangChainFactory

evaluation_router = APIRouter(prefix="/rag/evaluation", tags=["Evaluation"])

@evaluation_router.post("/groundtruth/generate")
async def generate_ground_truth():
    from application.ragas_service import RagasService
    #
    llms_infos = EnvHelper.get_llms_infos_from_env_config()
    llms = LangChainFactory.create_llms_from_infos(llms_infos)
    #testset = await RagasService.run_model_on_ground_truth_dataset_async(llms[0], samples_count= 3)
    testset = await RagasService.generate_test_dataset_from_documents_langchain_async(llms[0], None, samples_count= 3)
    return {"message": "Ground truth generated successfully"}
