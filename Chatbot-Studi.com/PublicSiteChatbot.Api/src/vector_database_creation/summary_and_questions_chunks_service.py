import json
import os
from langchain.schema import Document
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.file_helper import file
from common_tools.helpers.env_helper import EnvHelper
from common_tools.models.doc_w_summary_chunks_questions import DocWithSummaryChunksAndQuestions
from vector_database_creation.generate_documents_and_metadata import GenerateDocumentsAndMetadata
from vector_database_creation.summary_and_questions_creation import SummaryAndQuestionsChunksCreation

class SummaryAndQuestionsChunksService:

    async def build_trainings_docs_summary_chunked_by_questions_async(path, llm_and_fallback: list) -> list[Document]:
        trainings_objects = await SummaryAndQuestionsChunksService.build_trainings_objects_with_summaries_and_chunks_by_questions_async(path, llm_and_fallback)
        trainings_chunks_splitted_by_questions = SummaryAndQuestionsChunksService._build_trainings_chunks_splitted_by_questions_from_training_objs(trainings_objects)
        return trainings_chunks_splitted_by_questions

    async def build_trainings_objects_with_summaries_and_chunks_by_questions_async(path, llm_and_fallback: list):
        trainings_docs_by_sections = GenerateDocumentsAndMetadata.build_trainings_docs_by_sections(path)
        trainings_objects = await SummaryAndQuestionsChunksService.build_trainings_objects_with_summaries_and_chunks_by_questions_from_docs_async(
                                                                            path, 
                                                                            trainings_docs_by_sections, 
                                                                            llm_and_fallback)
        return trainings_objects
    
    async def build_trainings_objects_with_summaries_and_chunks_by_questions_from_docs_async(
            files_path: str, trainings_docs: list[Document], llm_and_fallback: list = None, load_existing_summaries_and_questions_from_file: bool = True
        ) -> list[DocWithSummaryChunksAndQuestions]:
        
        docs_with_summary_chunks_and_questions_file_path = os.path.join(files_path, 'trainings_summaries_chunks_and_questions_objects.json')
        trainings_objects: list[DocWithSummaryChunksAndQuestions] = None
        if load_existing_summaries_and_questions_from_file:
            trainings_objects = await SummaryAndQuestionsChunksService._load_trainings_objects_with_summaries_and_chunks_by_questions_async(docs_with_summary_chunks_and_questions_file_path)
            
        if not trainings_objects:
            trainings_objects = await SummaryAndQuestionsChunksCreation.generate_trainings_objects_with_summaries_and_chunks_by_questions_async(
                trainings_docs, llm_and_fallback, docs_with_summary_chunks_and_questions_file_path
            )

        # Verify that each loaded/generated trainings objects correspond to each provided trainings docs
        if trainings_docs:
            #trainings_docs_but_summaries = [obj for obj in trainings_docs if obj.metadata['training_info_type'] != 'summary']
            if len(trainings_docs) != len(trainings_objects):
                raise ValueError(f"Number of training objects ({len(trainings_objects)}) != number of training docs ({len(trainings_docs)})")
            for training_obj, training_doc in zip(trainings_objects, trainings_docs):
                if training_obj.doc_content != training_doc.page_content:
                    raise ValueError(f"Content mismatch in: {training_doc.metadata['name']}")
                for key, value in training_obj.metadata.items():
                    if key != 'id' and (key not in training_doc.metadata or training_doc.metadata[key] != value):
                        raise ValueError(f"Metadata mismatch in: {training_doc.metadata['name']} for key: {key}")
        return trainings_objects
   
    def _load_trainings_scraped_details_as_json(files_path: str) -> dict:
        files_str = file.get_files_paths_and_contents(os.path.join(files_path, 'scraped'))
        contents: dict = {}
        for file_path, content_str in files_str.items():
            content = json.loads(content_str)
            contents[content['title']] = content
        return contents

    async def _load_trainings_objects_with_summaries_and_chunks_by_questions_async(docs_with_summary_chunks_and_questions_file_path: str) -> list[DocWithSummaryChunksAndQuestions]:
        if file.exists(docs_with_summary_chunks_and_questions_file_path):
            docs_with_summary_chunks_and_questions_json = file.get_as_json(docs_with_summary_chunks_and_questions_file_path)
            trainings_objects = [DocWithSummaryChunksAndQuestions(**doc) for doc in docs_with_summary_chunks_and_questions_json]
            subject = 'trainings'
            txt.print(f">>> Loaded existing {len(trainings_objects)} docs about '{subject}' with: summary, chunks and questions from file: {docs_with_summary_chunks_and_questions_file_path}")
            trainings_objects = SummaryAndQuestionsChunksCreation._replace_metadata_id_by_doc_id(trainings_objects)
            return trainings_objects
        return None
    
    def _build_trainings_chunks_splitted_by_questions_from_training_objs(trainings_objects) -> list[Document]:
        trainings_chunks_and_questions_documents: list[Document] = []
        create_questions_from_data: bool = EnvHelper.get_is_questions_created_from_data()
        merge_questions_with_data: bool = EnvHelper.get_is_mixed_questions_and_data()

        if create_questions_from_data and merge_questions_with_data:
            for training_object in trainings_objects:
                trainings_chunks_and_questions_documents.extend(training_object.to_langchain_documents_chunked_summary_and_questions(True, True))
        else:
            for training_object in trainings_objects:
                trainings_chunks_and_questions_documents.extend(training_object.to_langchain_documents_chunked_summary_and_questions(True, False))
                if create_questions_from_data:
                    trainings_chunks_and_questions_documents.extend(training_object.to_langchain_documents_chunked_summary_and_questions(False, True))
        return trainings_chunks_and_questions_documents