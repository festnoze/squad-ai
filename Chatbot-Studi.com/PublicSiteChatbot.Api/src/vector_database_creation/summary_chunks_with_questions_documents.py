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

from common_tools.rag.rag_service import RagService

class SummaryWithQuestionsByChunkDocumentsService:
    def __init__(self) -> None:
        pass

    async def create_summary_and_questions_from_docs_single_step_async(self, llm_and_fallback: list, trainings_docs: list[Document]) -> DocWithSummaryChunksAndQuestions:
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

    async def create_summary_and_questions_from_docs_in_two_steps_async(self, llm_and_fallback: list, trainings_docs: list[Document]) -> DocWithSummaryChunksAndQuestions:
        test_training = trainings_docs[0]
        subject = test_training.metadata['type']
        name = test_training.metadata['name']
        doc_title = f'{subject} : "{name}".'
        doc_content = test_training.page_content
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
            doc_chunks=doc_chunks
        )
        return doc_summary1

    async def create_summary_and_questions_from_docs_in_three_steps_async(
        self,
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
                doc_chunks=doc_chunks
            ))
        return docs

    def build_docs_for_certifiers(self, data: list[dict]) -> list[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            item_name = item.get('name')
            metadata = {
                'id': item.get('id'),
                'type': 'certifieur',
                'name': item_name,
                'changed': item.get('changed')
            }
            doc = Document(page_content=item_name, metadata=metadata)
            docs.append(doc)
        return docs

    def build_docs_for_certifications(self, data: list[dict]) -> list[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            item_name = item.get('name')
            metadata = {
                'id': item.get('id'),
                'type': 'certification',
                'name': item_name,
                'changed': item.get('changed')
            }
            doc = Document(page_content=item_name, metadata=metadata)
            docs.append(doc)
        return docs

    def build_docs_for_diplomas(self, data: list[dict]) -> list[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            title = item.get('title', '')
            title = re.sub(r'\(.*?\)', '', title).replace('\n', ' ').replace(' ?', '').replace('Nos formations en ligne ', '').replace(' en ligne', '').replace('niveau', '').replace('Qu’est-ce qu’un ', '').replace(' +', '+').replace('Nos ', '').replace(' by Studi', '').strip()
            metadata = {
                'id': item.get('id'),
                'type': 'diplôme',
                'name': item.get('title'),
                'changed': item.get('changed')
            }
            related_paragraphs = item.get('related_infos', {}).get('paragraph', [])
            content = f"{title}\r\n{chr(92).join(related_paragraphs)}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs

    def build_docs_for_domains(self, data: list[dict]) -> list[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            item_name = item.get('name')
            metadata = {
                'id': item.get('id'),
                'type': 'domaine',
                'name': item_name,
                'changed': item.get('changed')
            }
            doc = Document(page_content=item_name, metadata=metadata)
            docs.append(doc)
        return docs

    def build_docs_for_subdomains(self, data: list[dict]) -> list[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            item_name = item.get('name')
            metadata = {
                'id': item.get('id'),
                'type': 'sous-domaine',
                'name': item_name,
                'changed': item.get('changed'),
                'domain_name': item.get('domain_name', item_name),
                'domain_id': item.get('related_ids').get('parent')[0] if item.get('related_ids') and item.get('related_ids').get('parent') else ''
            }
            doc = Document(page_content=item_name, metadata=metadata)
            docs.append(doc)
        return docs

    def build_docs_for_fundings(self, data: list[dict]) -> list[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            metadata = {
                'id': item.get('id'),
                'type': 'financement',
                'name': item.get('title'),
                'changed': item.get('changed')
            }
            related_paragraphs = item.get('related_infos', {}).get('paragraph', [])
            content = f"{item.get('title', '')}\r\n{chr(92).join(related_paragraphs)}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs

    def build_docs_for_jobs(self, data: list[dict], domains: list[dict]) -> list[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            job_title = item.get('title')
            metadata = {
                'id': item.get('id'),
                'type': 'métier',
                'name': job_title,
                'changed': item.get('changed'),
                'rel_ids': self.get_all_ids_as_str(item.get('related_ids', {}))
            }
            domain_id = item.get('related_ids', {}).get('domain', '')
            domain = ''
            if domain_id:
                domain = next((dom.get('name') for dom in domains if dom.get('id') == domain_id), '')
            content = f"Métier : '{metadata['name']}'. {('Domaine : ' + domain) if domain else ''}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs

    def build_trainings_docs(self, files_path: str, add_sub_sections: bool = True, add_full_doc: bool = False) -> list[Document]:
        domains_data = JsonHelper.load_from_json(os.path.join(files_path, 'domains.json'))
        sub_domains_data = JsonHelper.load_from_json(os.path.join(files_path, 'subdomains.json'))
        trainings_data = JsonHelper.load_from_json(os.path.join(files_path, 'trainings.json'))
        trainings_details = self.load_trainings_scraped_details_as_json(files_path)
        if not trainings_data: return []

        all_trainings_docs = []
        for training_data in trainings_data:
            training_title = training_data.get('title')
            related_ids = training_data.get('related_ids', {})
            metadata_common = {
                'id': training_data.get('id'),
                'type': 'formation',
                'name': training_title,
                'changed': training_data.get('changed'),
                'rel_ids': self.get_all_ids_as_str(related_ids)
            }
            sub_domain_id = related_ids.get('domain', '')
            subdoms = [s for s in sub_domains_data if s['id'] == sub_domain_id]
            if not subdoms or not any(subdoms) or not subdoms[0].get('related_ids') or not subdoms[0]['related_ids'].get('parent'):
                doms = [d for d in domains_data if d.get('id') == sub_domain_id]
                if doms and any(doms):
                    domain_id = doms[0]['id']
                else:
                    domain_id = ''
            else:
                domain_id = subdoms[0]['related_ids']['parent'][0]
            training_detail = trainings_details.get(training_title)
            training_url = ''
            if training_detail:
                if 'url' in training_detail:
                    training_url = training_detail['url']
                    metadata_common['url'] = training_url
                if 'academic_level' in training_detail:
                    metadata_common['academic_level'] = training_detail['academic_level']
            contents = [f"\n###{self.get_french_section(k)}###\n{Ressource.remove_curly_brackets(v)}" for k, v in training_data.get('attributes', {}).items()]
            content = f"Formation : {training_title}\nLien vers la page : {training_url}\n{chr(92).join(contents)}"
            metadata_summary = metadata_common.copy()
            metadata_summary['training_info_type'] = 'full'
            if training_detail and add_sub_sections:
                for section_name in training_detail:
                    if section_name not in ['url', 'title']:
                        content_detail = f"###{self.get_french_section(section_name)} de la formation : {training_title}###\n" + training_detail[section_name]
                        content += f"\n\n{content_detail}"
                        metadata_detail = metadata_common.copy()
                        metadata_detail['training_info_type'] = section_name
                        all_trainings_docs.append(Document(page_content=content_detail, metadata=metadata_detail))
            if add_full_doc:
                all_trainings_docs.append(Document(page_content=content, metadata=metadata_summary))
        return all_trainings_docs

    def build_all_but_trainings_documents(self, files_path: str) -> list[Document]:
        certifiers_data = JsonHelper.load_from_json(os.path.join(files_path, 'certifiers.json'))
        certifications_data = JsonHelper.load_from_json(os.path.join(files_path, 'certifications.json'))
        diplomas_data = JsonHelper.load_from_json(os.path.join(files_path, 'diplomas.json'))
        domains_data = JsonHelper.load_from_json(os.path.join(files_path, 'domains.json'))
        sub_domains_data = JsonHelper.load_from_json(os.path.join(files_path, 'subdomains.json'))
        fundings_data = JsonHelper.load_from_json(os.path.join(files_path, 'fundings.json'))
        jobs_data = JsonHelper.load_from_json(os.path.join(files_path, 'jobs.json'))

        certifiers_docs = self.build_docs_for_certifiers(certifiers_data)
        certifications_docs = self.build_docs_for_certifications(certifications_data)
        diplomas_docs = self.build_docs_for_diplomas(diplomas_data)
        domains_docs = self.build_docs_for_domains(domains_data)
        subdomains_docs = self.build_docs_for_subdomains(sub_domains_data)
        fundings_docs = self.build_docs_for_fundings(fundings_data)
        jobs_docs = self.build_docs_for_jobs(jobs_data, domains_data)
        
        docs: list[Document] = []
        docs.extend(certifiers_docs)
        docs.extend(certifications_docs)
        docs.extend(diplomas_docs)
        docs.extend(domains_docs)
        docs.extend(subdomains_docs)
        docs.extend(fundings_docs)
        docs.extend(jobs_docs)
        return docs

    def load_trainings_scraped_details_as_json(self, files_path: str) -> dict:
        files_str = file.get_files_paths_and_contents(os.path.join(files_path, 'scraped'))
        contents: dict = {}
        for file_path, content_str in files_str.items():
            content = json.loads(content_str)
            contents[content['title']] = content
        return contents

    async def load_trainings_objects_with_summaries_and_chunks_by_questions_async(self, docs_with_summary_chunks_and_questions_file_path: str) -> list[DocWithSummaryChunksAndQuestions]:
        if file.exists(docs_with_summary_chunks_and_questions_file_path):
            docs_with_summary_chunks_and_questions_json = file.get_as_json(docs_with_summary_chunks_and_questions_file_path)
            trainings_objects = [DocWithSummaryChunksAndQuestions(**doc) for doc in docs_with_summary_chunks_and_questions_json]
            subject = 'trainings'
            txt.print(f">>> Loaded existing {len(trainings_objects)} docs about '{subject}' with: summary, chunks and questions from file: {docs_with_summary_chunks_and_questions_file_path}")
            return trainings_objects
        return None
    
    async def generate_trainings_objects_with_summaries_and_chunks_by_questions_async(
            self, trainings_docs: list[Document], llm_and_fallback: list, docs_with_summary_chunks_and_questions_file_path: str
        ) -> list[DocWithSummaryChunksAndQuestions]:
        
        start = time.time()
        txt.print_with_spinner(f"Generating summaries, chunking and questions in 3 steps for each {len(trainings_docs)} documents")
        trainings_objects = await self.create_summary_and_questions_from_docs_in_three_steps_async(llm_and_fallback, trainings_docs, 50)
        
        docs_json = [doc.to_dict(include_full_doc=True) for doc in trainings_objects]
        file.write_file(docs_json, docs_with_summary_chunks_and_questions_file_path)
        
        elapsed_str = txt.get_elapsed_str(time.time() - start)
        txt.stop_spinner_replace_text(f"Finish generating for {len(trainings_objects)} documents. Done in: {elapsed_str}")
        
        return trainings_objects

    async def build_trainings_objects_with_summaries_and_chunks_by_questions_async(
            self, files_path: str, trainings_docs: list[Document], llm_and_fallback: list = None, load_existing_summaries_and_questions_from_file: bool = True
        ) -> list[DocWithSummaryChunksAndQuestions]:
        
        docs_with_summary_chunks_and_questions_file_path = os.path.join(files_path, 'trainings_summaries_chunks_and_questions_objects.json')
        trainings_objects = None
        if load_existing_summaries_and_questions_from_file:
            trainings_objects = await self.load_trainings_objects_with_summaries_and_chunks_by_questions_async(docs_with_summary_chunks_and_questions_file_path)
        
        if not trainings_objects:
            trainings_objects = await self.generate_trainings_objects_with_summaries_and_chunks_by_questions_async(
                trainings_docs, llm_and_fallback, docs_with_summary_chunks_and_questions_file_path
            )

        # Verify that trainings objects correspond to trainings docs
        if len(trainings_objects) != len(trainings_docs):
            raise ValueError(f"Number of training objects ({len(trainings_objects)}) != number of training docs ({len(trainings_docs)})")
        for training_obj, training_doc in zip(trainings_objects, trainings_docs):
            if training_obj.doc_content != training_doc.page_content:
                raise ValueError(f"Content mismatch in: {training_doc.metadata['name']}")
            if training_obj.metadata != training_doc.metadata:
                raise ValueError(f"Metadata mismatch in: {training_doc.metadata['name']}")
        
        # for training_obj in trainings_objects:
        #     trainings_doc = [doc for doc in trainings_docs if doc.metadata['id'] == training_obj.metadata['id']]
        #     if not trainings_doc:
        #         raise ValueError(f"Could not find the training doc with id: {training_obj.metadata['id']}")
        #     training_doc = trainings_doc[0]
        #     if training_obj.doc_content != training_doc.page_content:
        #         raise ValueError(f"Content mismatch in: {training_doc.metadata['name']}")
        #     if training_obj.metadata != training_doc.metadata:
        #         raise ValueError(f"Metadata mismatch in: {training_doc.metadata['name']}")           
        return trainings_objects
    
    async def build_trainings_objects_async(self, path):
        trainings_docs_raw = self.build_trainings_docs(path)
        trainings_objects = await self.build_trainings_objects_with_summaries_and_chunks_by_questions_async(path, trainings_docs_raw)
        return trainings_objects
    
    async def build_trainings_docs_with_summary_chunked_by_questions_async(self, path):
        trainings_docs_raw = self.build_trainings_docs(path)
        trainings_objects = await self.build_trainings_objects_with_summaries_and_chunks_by_questions_async(path, trainings_docs_raw)
        trainings_chunks_splitted_by_questions = self.build_trainings_docs_from_objs(trainings_objects)

        # Display all chunks with questions by training doc
        for training_doc_raw in trainings_docs_raw[:5]:
            trainings_docs = [doc for doc in trainings_chunks_splitted_by_questions 
                              if doc.metadata['name'] == training_doc_raw.metadata['name']
                              and doc.metadata['training_info_type'] == training_doc_raw.metadata['training_info_type']]
            print("##################################################")
            print(f"For training doc: {training_doc_raw.metadata['name']}")
            print(f"For training type: '{training_doc_raw.metadata['training_info_type']}'")
            print(f"with content: {training_doc_raw.page_content}")
            print("--------------------------------------------------")
            print(f"Found {len(trainings_docs)} corresponding docs with summary and questions. Here are the summaries only:")
            for training_doc in trainings_docs:
                if not '### Réponses ###' in training_doc.page_content:
                    raise ValueError(f"Could not find the '### Réponses ###' in: {training_doc.metadata['name']}")
                splitted_training_doc = training_doc.page_content.split('### Réponses ###')
                print(f"=> {splitted_training_doc[1]}")
                print(f"{splitted_training_doc[0]}")

        # Verify that trainings docs correspond to trainings docs with summary and questions
        # for training_doc_summary_with_questions in trainings_docs_with_summary_and_questions:
        #     trainings_docs = [doc for doc in trainings_docs_raw 
        #                       if doc.metadata['name'] == training_doc_summary_with_questions.metadata['name']
        #                       and doc.metadata['training_info_type'] == training_doc_summary_with_questions.metadata['training_info_type']]
        #     if not trainings_docs:
        #         raise ValueError(f"Could not find the training doc with name: {training_doc_summary_with_questions.metadata['name']} and type: {training_doc_summary_with_questions.metadata['training_info_type']}")
        #     if len(trainings_docs) > 1:
        #         raise ValueError(f"Found more than one training doc with name: {training_doc_summary_with_questions.metadata['name']} and type: {training_doc_summary_with_questions.metadata['training_info_type']}")
        #     if trainings_docs[0].metadata != training_doc_summary_with_questions.metadata:
        #         raise ValueError(f"Metadata mismatch in: {training_doc_summary_with_questions.metadata['name']}")
            
        return trainings_chunks_splitted_by_questions
    
    async def generate_summaries_and_questions_for_documents_async(self, files_path: str, llm_and_fallback: list, create_questions_from_data: bool = True , merge_questions_with_data: bool = True) -> list[Document]:
        all_documents: list[Document] = []
        all_but_trainings_documents = self.build_all_but_trainings_documents(files_path)
        all_documents.extend(all_but_trainings_documents)

        trainings_docs = self.build_trainings_docs(files_path)
        #all_documents.extend(trainings_docs)

        trainings_objects = await self.build_trainings_objects_with_summaries_and_chunks_by_questions_async(files_path, trainings_docs, llm_and_fallback)
                
        trainings_chunks_and_questions_documents = self.build_trainings_docs_from_objs(trainings_objects, create_questions_from_data, merge_questions_with_data)
        all_documents.extend(trainings_chunks_and_questions_documents)
        
        return all_documents

    def build_trainings_docs_from_objs(self, trainings_objects, create_questions_from_data: bool = True, merge_questions_with_data: bool = True):
        trainings_chunks_and_questions_documents = []
        if create_questions_from_data and merge_questions_with_data:
            for training_object in trainings_objects:
                trainings_chunks_and_questions_documents.extend(training_object.to_langchain_documents_chunked_summary_and_questions(True, True))
        else:
            for training_object in trainings_objects:
                trainings_chunks_and_questions_documents.extend(training_object.to_langchain_documents_chunked_summary_and_questions(True, False))
                if create_questions_from_data:
                    trainings_chunks_and_questions_documents.extend(training_object.to_langchain_documents_chunked_summary_and_questions(False, True))
        return trainings_chunks_and_questions_documents
    

    section_to_french:dict = None # Singleton prop. containing the static mapping of section names to their french equivalent.
    def get_french_section(self, section_name: str) -> str:
        if not SummaryWithQuestionsByChunkDocumentsService.section_to_french:
            self.init_sections_names_french_mapping()

        if section_name in SummaryWithQuestionsByChunkDocumentsService.section_to_french:
            return SummaryWithQuestionsByChunkDocumentsService.section_to_french[section_name]
        else:
            raise ValueError(f"Unhandled section name: {section_name} in get_french_section")

    def init_sections_names_french_mapping(self):
        SummaryWithQuestionsByChunkDocumentsService.section_to_french = {
                'title': "Titre",
                'academic_level': "Niveau académique",
                'content': "Contenu",
                'certification': "Certification",
                'diploma': "Diplôme",
                'diploma_name': "Diplôme",
                'domain': "Domaine",
                'job': "Métiers",
                'metiers': "Métiers",
                'funding': "Financements",
                'goal': "Objectifs",
                'summary': "Résumé",
                'header-training': "Informations générales",
                'bref': "Description en bref",
                'cards-diploma': "Diplômes obtenus",
                'programme': "Programme",
                'financement': "Financements possibles",
                'methode': "Méthode d'apprentissage Studi",
                'modalites': "Modalités",
                'simulation': "Simulation de formation",
                # Sections from attributes
                'accessibility': "Accessibilité",
                'accompaniment': "Accompagnement",
                'certif': "Certification",
                'context': "Contexte",
                'entry_prerequisites': "Pré-requis d'entrée",
                'equivalences_bridges': "Equivalences et passerelles",
                'eval_methods': "Méthodes d'évaluation",
                'exam': "Examen",
                'exam_periods': "Périodes d'examen",
                'flow': "Déroulement",
                'goals': "Objectifs",
                'metatag': "Etiquettes (tags)",
                'postsecondary_studies': "Études postsecondaires",
                'prerequisites': "Pré-requis",
                'professional_experience': "Expérience professionnelle",
                'program_brut': "Programme",
                'registration': "Inscription",
                'skills_block_validation': "Validation des blocs de compétences",
                'title_rncp': "Titre RNCP",
                'nom_du_titre_support_rncp': "Nom du support RNCP",
                'work_study_missions': "Missions en alternance",
                'work_study_duration': "Durée en alternance",
                'average_salary_disclaimer': "Salaire moyen",
                'wyg_certifier_link': "Lien de certification WYG",
                'hook': "Accroche",
                'pedago_modalities': "Modalités pédagogiques",
                'code_rncp': "Code RNCP"
            }
    
    def get_list_with_items_as_str(self, lst: list):
        if not lst:
            return []
        return [str(uid) for uid in lst]
    
    def get_all_ids_as_str(self, related_ids):
        all_ids = []
        # Iterate over all keys and values in related_ids
        for key, value in related_ids.items():
            if isinstance(value, list):
                # Extend the list if the value is a list of IDs
                all_ids.extend(value)
            elif isinstance(value, str):
                # Add the single string value directly
                all_ids.append(value)

        # Join all IDs into a single comma-separated string
        all_ids_str = ",".join(all_ids)
        return all_ids_str
    
    # Method to test the 3 ways of generating summaries, chunks and questions (use to be in 'available services')
    async def test_different_splitting_of_summarize_chunks_and_questions_creation_async(rag_service:RagService, files_path):
        summary_w_questions_service = SummaryWithQuestionsByChunkDocumentsService()
        trainings_docs = summary_w_questions_service.load_trainings_scraped_details_as_json(files_path)

        txt.print("-"*70)
        start = time.time()
        summary_1_step = await summary_w_questions_service.create_summary_and_questions_from_docs_single_step_async([rag_service.llm_1, rag_service.llm_2], trainings_docs)
        summary_1_step_elapsed_str = txt.get_elapsed_str(time.time() - start)
        
        start = time.time()
        summary_2_steps = await summary_w_questions_service.create_summary_and_questions_from_docs_in_two_steps_async([rag_service.llm_1, rag_service.llm_2], trainings_docs)
        summary_2_steps_elapsed_str = txt.get_elapsed_str(time.time() - start)

        start = time.time()
        summary_3_steps = await summary_w_questions_service.create_summary_and_questions_from_docs_in_three_steps_async([rag_service.llm_1, rag_service.llm_2], trainings_docs)
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