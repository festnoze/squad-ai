import json
import os
import re
import time
from typing import Union

from langchain.schema import Document
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.file_helper import file
from common_tools.helpers.json_helper import JsonHelper
from common_tools.helpers.llm_helper import Llm
from common_tools.models.doc_w_summary_chunks_questions import Question, DocChunk, DocWithSummaryChunksAndQuestions, DocWithSummaryChunksAndQuestionsPydantic, DocQuestionsByChunkPydantic
from common_tools.helpers.ressource_helper import Ressource

from common_tools.RAG.rag_service import RagService

class SummaryAndQuestionsChunksCreation:

    async def generate_trainings_objects_with_summaries_and_chunks_by_questions_async(
            trainings_docs: list[Document], llm_and_fallback: list, docs_with_summary_chunks_and_questions_file_path: str
        ) -> list[DocWithSummaryChunksAndQuestions]:
        
        start = time.time()
        txt.print_with_spinner(f"Generating summaries, chunking and questions in 3 steps for each {len(trainings_docs)} documents")
        trainings_objects = await SummaryAndQuestionsChunksCreation.create_summary_and_questions_from_docs_in_three_steps_async(llm_and_fallback, trainings_docs, 50)
        
        docs_json = [doc.to_dict(include_full_doc=True) for doc in trainings_objects]
        file.write_file(docs_json, docs_with_summary_chunks_and_questions_file_path)
        
        elapsed_str = txt.get_elapsed_str(time.time() - start)
        txt.stop_spinner_replace_text(f"Finish generating for {len(trainings_objects)} documents. Done in: {elapsed_str}")
        
        trainings_objects = SummaryAndQuestionsChunksCreation._replace_metadata_id_by_doc_id(trainings_objects)
        return trainings_objects
    
    def _replace_metadata_id_by_doc_id(trainings_objects: list[DocWithSummaryChunksAndQuestions]):
        for doc in trainings_objects:
            doc.metadata['id'] = doc.metadata['doc_id']
        return trainings_objects
    
    async def create_summary_and_questions_from_docs_single_step_async(llm_and_fallback: list, trainings_docs: list[Document]) -> DocWithSummaryChunksAndQuestions:
        test_training = trainings_docs[0]
        subject = test_training.metadata['type']
        name = test_training.metadata['name']
        doc_title = f'{subject} : "{name}".'
        prompt_summarize_doc = Ressource.load_with_replaced_variables(
            file_name='document_summarize_create_chunks_and_corresponding_questions.french.txt',
            variables_values={
                'doc_title': doc_title,
                'doc_content': test_training.page_content
            }
        )
        prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
            prompt_summarize_doc,
            DocWithSummaryChunksAndQuestionsPydantic,
            DocWithSummaryChunksAndQuestions
        )
        response_1 = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async(
            'Summarize documents by batches',
            llm_and_fallback,
            output_parser,
            10,
            *[prompt_for_output_parser]
        )
        doc_summary1 = DocWithSummaryChunksAndQuestions(doc_content=test_training.page_content, **response_1[0])
        return doc_summary1

    async def create_summary_and_questions_from_docs_in_two_steps_async(llm_and_fallback: list, trainings_docs: list[Document]) -> DocWithSummaryChunksAndQuestions:
        test_training = trainings_docs[0]
        subject = test_training.metadata['type']
        name = test_training.metadata['name']
        doc_title = f'{subject} : "{name}".'
        doc_content = test_training.page_content
        doc_metadata = test_training.metadata
        variables_values = {
            'doc_title': doc_title,
            'doc_content': doc_content
        }
        prompt_summarize_doc = Ressource.load_with_replaced_variables(
            file_name='document_summarize.french.txt',
            variables_values=variables_values
        )
        resp = await Llm.invoke_chain_with_input_async('Summarize document', llm_and_fallback[0], prompt_summarize_doc)
        doc_summary = Llm.get_content(resp)
        prompt_doc_chunks_and_questions = Ressource.load_with_replaced_variables(
            file_name='document_create_chunks_and_corresponding_questions.french.txt',
            variables_values=variables_values
        )
        prompt_doc_chunks_and_questions_for_output_parser, chunks_and_questions_output_parser = Llm.get_prompt_and_json_output_parser(
            prompt_doc_chunks_and_questions,
            DocQuestionsByChunkPydantic,
            DocWithSummaryChunksAndQuestions
        )
        doc_chunks_and_questions_response = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async(
            'Chunks & questions from documents by batches',
            llm_and_fallback,
            chunks_and_questions_output_parser,
            10,
            *[prompt_doc_chunks_and_questions_for_output_parser]
        )
        doc_chunks = doc_chunks_and_questions_response[0]['doc_chunks']
        doc_summary1 = DocWithSummaryChunksAndQuestions(
            doc_content=doc_content,
            doc_summary=doc_summary,
            doc_chunks=doc_chunks,
            metadata=doc_metadata
        )
        return doc_summary1

    async def create_summary_and_questions_from_docs_in_three_steps_async(
        llm_and_fallback: list,
        trainings_docs: list[Document],
        batch_size: int = 50
    ) -> list[DocWithSummaryChunksAndQuestions]:
        prompts_summarize_doc = []
        for training_doc in trainings_docs:
            doc_title = f"{training_doc.metadata['type']} : \"{training_doc.metadata['name']}\"."
            doc_content = training_doc.page_content
            prompt_summarize_doc = Ressource.load_with_replaced_variables(
                file_name='document_summarize.french.txt',
                variables_values={'doc_title': doc_title, 'doc_content': doc_content}
            )
            prompts_summarize_doc.append(prompt_summarize_doc)
        summarized_docs_response = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async(
            f'Summarize {len(trainings_docs)} documents',
            llm_and_fallback,
            None,
            batch_size,
            *prompts_summarize_doc
        )
        docs_summaries = [Llm.get_content(summarized_doc) for summarized_doc in summarized_docs_response]
        prompts_docs_chunks = []
        for i in range(len(trainings_docs)):
            prompt_doc_chunks = Ressource.load_with_replaced_variables(
                file_name='document_extract_chunks.french.txt',
                variables_values={'doc_title': trainings_docs[i].metadata['name'], 'doc_content': docs_summaries[i]}
            )
            prompts_docs_chunks.append(prompt_doc_chunks)
        chunking_docs_response = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async(
            f'Chunking {len(trainings_docs)} documents',
            llm_and_fallback,
            None,
            batch_size,
            *prompts_docs_chunks
        )
        docs_chunks_json = [Llm.extract_json_from_llm_response(chunking_doc) for chunking_doc in chunking_docs_response]
        chunks_by_docs = [[chunk['chunk_content'] for chunk in doc_chunks] for doc_chunks in docs_chunks_json]
        prompts_chunks_questions = []
        prompt_create_questions_for_chunk = Ressource.load_ressource_file('document_create_questions_for_a_chunk.french.txt')
        for i in range(len(trainings_docs)):
            for doc_chunk in chunks_by_docs[i]:
                prompt_chunk_questions = Ressource.replace_variables(
                    prompt_create_questions_for_chunk,
                    {'doc_title': trainings_docs[i].metadata['name'], 'doc_chunk': doc_chunk}
                )
                prompts_chunks_questions.append(prompt_chunk_questions)
        doc_chunks_questions_response = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async(
            f'Generate questions for {sum([len(chunks) for chunks in chunks_by_docs])} chunks',
            llm_and_fallback,
            None,
            batch_size,
            *prompts_chunks_questions
        )
        idx = 0
        docs = []
        for i in range(len(trainings_docs)):
            doc_chunks = []
            for j in range(len(chunks_by_docs[i])):
                try:
                    chunk_questions = Llm.extract_json_from_llm_response(doc_chunks_questions_response[idx])
                except Exception as e:
                    txt.print(f"<<<<< Error on doc {i} chunk {j} with error: {e}>>>>>>")
                    chunk_questions = []
                chunk_text = chunks_by_docs[i][j]
                q_objects = [Question(q['question']) for q in chunk_questions]
                doc_chunks.append(DocChunk(chunk_text, q_objects))
                idx += 1
            docs.append(DocWithSummaryChunksAndQuestions(
                doc_content=trainings_docs[i].page_content,
                doc_summary=docs_summaries[i],
                doc_chunks=doc_chunks,
                metadata=trainings_docs[i].metadata
            ))
        return docs

    # Method to test the 3 ways of generating summaries, chunks and questions (use to be in 'available services')
    async def test_different_splitting_of_summarize_chunks_and_questions_creation_async(rag_service:RagService, files_path):

        trainings_docs = SummaryAndQuestionsChunksCreation.load_trainings_scraped_details_as_json(files_path)

        txt.print("-"*70)
        start = time.time()
        summary_1_step = await SummaryAndQuestionsChunksCreation.create_summary_and_questions_from_docs_single_step_async([rag_service.llm_1, rag_service.llm_2], trainings_docs)
        summary_1_step_elapsed_str = txt.get_elapsed_str(time.time() - start)
        
        start = time.time()
        summary_2_steps = await SummaryAndQuestionsChunksCreation.create_summary_and_questions_from_docs_in_two_steps_async([rag_service.llm_1, rag_service.llm_2], trainings_docs)
        summary_2_steps_elapsed_str = txt.get_elapsed_str(time.time() - start)

        start = time.time()
        summary_3_steps = await SummaryAndQuestionsChunksCreation.create_summary_and_questions_from_docs_in_three_steps_async([rag_service.llm_1, rag_service.llm_2], trainings_docs)
        summary_3_steps_elapsed_str = txt.get_elapsed_str(time.time() - start)
        
        txt.print("-"*70)
        summary_1_step.display_to_terminal()
        txt.print(f"Single step summary generation took {summary_1_step_elapsed_str}")
        txt.print("-"*70)

        summary_2_steps.display_to_terminal()
        txt.print(f"Two steps summary generation took {summary_2_steps_elapsed_str}")
        txt.print("-"*70)

        summary_3_steps[0].display_to_terminal()
        txt.print(f"Three steps summary generation took {summary_3_steps_elapsed_str}")
        txt.print("-"*70)