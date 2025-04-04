import os
import time
from typing import Any, Dict
from fastapi import APIRouter
from application.evaluation_service import EvaluationService
from common_tools.helpers.env_helper import EnvHelper
from common_tools.helpers.file_helper import file
from common_tools.langchains.langchain_factory import LangChainFactory
from common_tools.models.embedding_model import EmbeddingModel
from common_tools.models.embedding_model_factory import EmbeddingModelFactory
from common_tools.models.doc_w_summary_chunks_questions import DocWithSummaryChunksAndQuestions
from vector_database_creation.summary_and_questions_chunks_service import SummaryAndQuestionsChunksService

evaluation_router = APIRouter(prefix="/rag/evaluation", tags=["Evaluation"])
output_path:str = './outputs'

@evaluation_router.post("/create-ground-truth-dataset-run-inference-and-evaluate")
async def create_q_and_a_dataset_then_run_inference_then_evaluate(samples_count_by_metadata: int = 20, batch_size: int = 20) -> Dict[str, Any]:
    
    testset_sample =                             await EvaluationService.create_q_and_a_sample_dataset_from_existing_summary_and_questions_objects_async(samples_count_by_metadata)
    start_inference = time.time()
    testset_sample_with_inference_results =      await EvaluationService.add_to_dataset_retrieved_chunks_and_augmented_generation_from_RAG_inference_execution_async(testset_sample, batch_size)
    end_inference = time.time()
    evaluation_results, evaluation_results_url = await EvaluationService.run_ragas_evaluation_and_upload_async(testset_sample_with_inference_results)
    end = time.time()

    print(f"RAG inference time: {(end_inference - start_inference):2f} seconds")
    print(f"Evaluation time: {(end - end_inference):2f} seconds")
    print(f"Total elapsed time: {(end - start_inference):2f} seconds")
    
    return {"dataset": testset_sample, "inference": testset_sample_with_inference_results, "evaluation URL": evaluation_results_url, "evaluation": evaluation_results}

@evaluation_router.post("/create-QA-dataset")
async def create_q_and_a_dataset_from_existing_summary_and_questions_objects_async(samples_count_by_metadata: int = 10, output_file: str = None) -> Dict[str, Any]:
    result = await EvaluationService.create_q_and_a_sample_dataset_from_existing_summary_and_questions_objects_async(samples_count_by_metadata, './outputs')
    
    if output_file:
        import pandas as pd
        file.write_file(result, os.path.join(output_path, output_file))
        # Transform the array of dicts into a CSV file using pandas
        df = pd.DataFrame(result)  # Convert the list of dictionaries to a DataFrame
        csv_file_path = os.path.join(output_path, output_file.replace('.json', '.csv'))
        df.to_csv(csv_file_path, index=False, sep=';')  # Save the DataFrame as a CSV file
    return result[:10]  # Return only the first 10 items for brevity

@evaluation_router.post("/run-inference")
async def run_questions_dataset_through_rag_inference_pipeline_and_save_async(input_file: str = "QA-dataset.json", output_file: str = None) -> Dict[str, Any]:
    dataset = file.get_as_json(input_file)
    result = await EvaluationService.add_to_dataset_retrieved_chunks_and_augmented_generation_from_RAG_inference_execution_async(dataset)
    
    if output_file:
        file.write_file(result, os.path.join(output_path, output_file))
    return result

@evaluation_router.post("/evaluate")
async def run_ragas_evaluation_and_upload_async(input_file: str = "inference.json") -> Dict[str, Any]:
    result = await EvaluationService.run_ragas_evaluation_and_upload_async(input_file)
    return result

@evaluation_router.post("/groundtruth/generate")
async def generate_ground_truth():
    from application.ragas_service import RagasService
    #
    llms_infos = EnvHelper.get_llms_infos_from_env_config()
    llms = LangChainFactory.create_llms_from_infos(llms_infos)
    embedding_model = EnvHelper.get_embedding_model()
    EmbeddingModelFactory.create_instance(embedding_model)
    #
    trainings_docs_with_summary_chunked_by_questions:list[DocWithSummaryChunksAndQuestions] = await SummaryAndQuestionsChunksService.build_trainings_objects_with_summaries_and_chunks_by_questions_from_docs_async(output_path, None, llms)
    trainings_samples_count = 5
    #trainings_samples = random.sample(trainings_docs, trainings_samples_count) if trainings_samples_count else trainings_docs

    # Works:
    testset = await RagasService.build_a_sample_dataset_from_trainings_objs_file_and_RAG_inference_execution_async(samples_count= trainings_samples_count)
    eval_res = RagasService.run_ragas_evaluation(llms[0], testset)
    return {"testset": testset}

    docs_by_chunks = [doc.to_langchain_documents_chunked_summary_and_questions() for doc in trainings_docs_with_summary_chunked_by_questions]
    flatten_docs = []
    for doc in docs_by_chunks:
        flatten_docs.extend(doc)

    testset = await RagasService.generate_test_dataset_from_documents_langchain_async(
                                    flatten_docs,
                                    llms[0], 
                                    embedding_model, 
                                    samples_count= trainings_samples_count)
    
    RagasService.run_ragas_evaluation(llms[0], testset)

    knowledge_graph = RagasService.generate_or_load_ragas_knowledge_graph_from_documents(
                                    trainings_docs_with_summary_chunked_by_questions,
                                    llms[0], 
                                    embedding_model, 
                                    samples_count= trainings_samples_count)
    
    testset = RagasService.generate_tests_from_knowledge_graph(knowledge_graph, llms[0], embedding_model, trainings_samples_count)
    
    return {"testset": testset.to_dict()}