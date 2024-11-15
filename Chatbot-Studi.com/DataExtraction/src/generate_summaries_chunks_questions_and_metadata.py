import json
import os
import re
#
from langchain.schema import Document
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.file_helper import file
from common_tools.helpers.json_helper import JsonHelper
from common_tools.helpers.llm_helper import Llm
from common_tools.models.doc_w_summary_chunks_questions import Question, DocChunk, DocWithSummaryChunksAndQuestions, DocWithSummaryChunksAndQuestionsPydantic, DocQuestionsByChunkPydantic
from common_tools.helpers.ressource_helper import Ressource

class GenerateDocumentsSummariesChunksQuestionsAndMetadata:
    def __init__(self):
        pass

    async def create_summary_and_questions_from_docs_single_step_async(self, llm_and_fallback:list, trainings_docs:list[Document]):
        txt.print('Warning: Only process the 1st document for now.')
        test_training = trainings_docs[0]
        subject = test_training.metadata['type']
        name = test_training.metadata['name']
        doc_title = f'{subject} : "{name}".'
        prompt_summarize_doc = Ressource.load_with_replaced_variables(
                    file_name= 'document_summarize_create_chunks_and_corresponding_questions.french.txt',
                    variables_values= {
                        'doc_title': doc_title, 
                        'doc_content': test_training.page_content
                    }
            )
        prompt_for_output_parser, output_parser = Llm.get_prompt_and_json_output_parser(
                prompt_summarize_doc, DocWithSummaryChunksAndQuestionsPydantic, DocWithSummaryChunksAndQuestions)
        
        response_1 = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async(
                        'Summarize documents by batches', 
                        llm_and_fallback, 
                        output_parser, 10, *[prompt_for_output_parser])
        doc_summary1 = DocWithSummaryChunksAndQuestions(doc_content= test_training.page_content, **response_1[0])
        return doc_summary1

    async def create_summary_and_questions_from_docs_in_two_steps_async(self, llm_and_fallback:list, trainings_docs):
        txt.print('Warning: Only process the 1st document for now.')
        test_training = trainings_docs[0]
        subject = test_training.metadata['type']
        name = test_training.metadata['name']
        doc_title = f'{subject} : "{name}".'
        doc_content = test_training.page_content
        variables_values= {
                        'doc_title': doc_title, 
                        'doc_content': doc_content
                    }
        
        # Step 1: Summarize document
        prompt_summarize_doc = Ressource.load_with_replaced_variables(
                    file_name= 'document_summarize.french.txt',
                    variables_values= variables_values)
                
        resp = await Llm.invoke_chain_with_input_async('Summarize document', llm_and_fallback[0], prompt_summarize_doc)
        doc_summary = Llm.get_content(resp)
        txt.print(doc_summary[:500])

        # Step 2: Split document in chunks with associated questions
        prompt_doc_chunks_and_questions = Ressource.load_with_replaced_variables(
                        file_name= 'document_create_chunks_and_corresponding_questions.french.txt',
                        variables_values= variables_values)
        
        prompt_doc_chunks_and_questions_for_output_parser, chunks_and_questions_output_parser = Llm.get_prompt_and_json_output_parser(
                prompt_doc_chunks_and_questions, DocQuestionsByChunkPydantic, DocWithSummaryChunksAndQuestions)
        
        doc_chunks_and_questions_response = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async(
                        'Chunks & questions from documents by batches', 
                        llm_and_fallback, 
                        chunks_and_questions_output_parser, 
                        10,
                        *[prompt_doc_chunks_and_questions_for_output_parser])
        
        doc_chunks = doc_chunks_and_questions_response[0]['doc_chunks']        
        doc_summary1 = DocWithSummaryChunksAndQuestions(doc_content= doc_content, doc_summary=doc_summary, doc_chunks=doc_chunks)
        return doc_summary1

    async def create_summary_and_questions_from_docs_in_three_steps_async(self, llm_and_fallback:list, trainings_docs, batch_size:int = 50):      
        # Step 1: Summarize document
        prompts_summarize_doc = []
        for training_doc in trainings_docs:
            doc_title = f'{training_doc.metadata['type']} : "{training_doc.metadata['name']}".'
            doc_content = training_doc.page_content            
            prompt_summarize_doc = Ressource.load_with_replaced_variables(
                                    file_name= 'document_summarize.french.txt',
                                    variables_values= {'doc_title': doc_title, 'doc_content': doc_content})       
            prompts_summarize_doc.append(prompt_summarize_doc)

        summarized_docs_response = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async(f'Summarize {len(trainings_docs)} documents', llm_and_fallback, None, batch_size, *prompts_summarize_doc)
        
        docs_summaries = [Llm.get_content(summarized_doc) for summarized_doc in summarized_docs_response]
        
        # Step 2: Split document's summary in chunks
        prompts_docs_chunks = []
        for i in range(len(trainings_docs)):
            prompt_doc_chunks = Ressource.load_with_replaced_variables(
                                    file_name= 'document_extract_chunks.french.txt', 
                                    variables_values= {'doc_title': trainings_docs[i].metadata['name'], 'doc_content': docs_summaries[i]})
            prompts_docs_chunks.append(prompt_doc_chunks)

        chunking_docs_response = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async(f'Chunking {len(trainings_docs)} documents', llm_and_fallback, None, batch_size, *prompts_docs_chunks)
        
        docs_chunks_json = [Llm.extract_json_from_llm_response(chunking_doc) for chunking_doc in chunking_docs_response]
        chunks_by_docs = [[chunk['chunk_content'] for chunk in doc_chunks] for doc_chunks in docs_chunks_json] 

        # Step 3: Create questions for each chunk of each document
        prompts_chunks_questions = []
        prompt_create_questions_for_chunk = Ressource.load_ressource_file('document_create_questions_for_a_chunk.french.txt')
        for i in range(len(trainings_docs)):
            for doc_chunk in chunks_by_docs[i]:
                prompt_chunk_questions = Ressource.replace_variables(prompt_create_questions_for_chunk, {'doc_title': trainings_docs[i].metadata['name'], 'doc_chunk': doc_chunk})
                prompts_chunks_questions.append(prompt_chunk_questions)

        doc_chunks_questions_response = await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async(f'Generate questions for {sum([len(chunks) for chunks in chunks_by_docs])} chunks', llm_and_fallback, None, batch_size, *prompts_chunks_questions)   
        
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
                chunk_questions = [Question(chunk_question['question']) for chunk_question in chunk_questions]
                doc_chunks.append(DocChunk(chunk_text, chunk_questions))
                idx += 1
            docs.append(DocWithSummaryChunksAndQuestions(doc_content= trainings_docs[i].page_content, doc_summary=docs_summaries[i], doc_chunks=doc_chunks))
        return docs
    
    def load_all_docs_summaries_as_json(self, path: str) -> list[Document]:
        all_docs = []
        txt.print_with_spinner(f"Build all Langchain documents summaries ...")

        # Process certifiers
        certifiers_data = JsonHelper.load_from_json(os.path.join(path, 'certifiers.json'))
        certifications_data = JsonHelper.load_from_json(os.path.join(path, 'certifications.json'))
        diplomas_data = JsonHelper.load_from_json(os.path.join(path, 'diplomas.json'))
        domains_data = JsonHelper.load_from_json(os.path.join(path, 'domains.json'))
        sub_domains_data = JsonHelper.load_from_json(os.path.join(path, 'subdomains.json'))

        # # Process jobs
        # jobs_data = JsonHelper.load_from_json(os.path.join(path, 'jobs.json'))
        # jobs_docs, all_jobs_names = self.process_jobs(jobs_data, domains_data)
        # all_docs.extend(jobs_docs)

    def load_and_process_trainings(self, path: str) -> list[Document]:
        all_docs = []
        # Load all needed infos from files
        domains_data = JsonHelper.load_from_json(os.path.join(path, 'domains.json'))
        sub_domains_data = JsonHelper.load_from_json(os.path.join(path, 'subdomains.json'))
        trainings_data = JsonHelper.load_from_json(os.path.join(path, 'trainings.json'))
        trainings_details = self.load_trainings_details_as_json(path)

        trainings_docs, all_trainings_names = self.process_trainings(trainings_data, trainings_details, all_docs, domains_data, sub_domains_data)
        all_docs.extend(trainings_docs)

        return all_docs
    
    def load_trainings_details_as_json(self, path: str) -> dict:
        files_str = file.get_files_paths_and_contents(os.path.join(path, 'scraped/'))
        contents = {}
        for file_path, content_str in files_str.items():
            filename = file_path.split('/')[-1].split('.')[0]
            content = json.loads(content_str)
            contents[content['title']] = content
        return contents
        # idx = 0
        # for key, sections in contents.items():
        #     idx+=1
        #     if idx > 5: break
        #     for section_name, section_content in sections.items():
        #         txt.print(f"## {section_name} ##")
        #         txt.print(section_content)#f"{section_content[:500]} ...")
        #         txt.print(f" ")
        #     txt.print(f"---------------------")

    def process_certifiers(self, data: list[dict]) -> list[Document]:
        if not data:
            return []
        all_certifiers_names = set()
        docs = []
        for item in data:
            item_name = item.get('name')
            all_certifiers_names.add(item_name)
            metadata = {
                "id": item.get("id"),
                "type": "certifieur",
                "name": item_name,
                "changed": item.get("changed"),
            }
            doc = Document(page_content=item_name, metadata=metadata)
            docs.append(doc)
        return docs, list(all_certifiers_names)
    
    def process_certifications(self, data: list[dict]) -> list[Document]:
        if not data:
            return []
        all_certifications_names = set()
        docs = []
        for item in data:
            item_name = item.get('name')
            all_certifications_names.add(item_name)
            metadata = {
                "id": item.get("id"),
                "type": "certification",
                "name": item_name,
                "changed": item.get("changed"),
            }
            doc = Document(page_content=item_name, metadata=metadata)
            docs.append(doc)
        return docs, list(all_certifications_names)

    def process_diplomas(self, data: list[dict]) -> list[Document]:
        if not data:
            return []
        docs = []
        all_diplomas_names = set()
        for item in data:
            title = item.get("title", '')
            title = re.sub(r'\(.*?\)', '', title).replace("\n", " ").replace(" ?", "").replace("Nos formations en ligne ", "").replace(" en ligne", "").replace("niveau", "").replace("Qu’est-ce qu’un ", "").replace(" +", "+").replace("Nos ", "").replace(" by Studi", "").strip()
            all_diplomas_names.add(title)
            metadata = {
                "id": item.get("id"),
                "type": "diplôme",
                "name": item.get("title"),
                "changed": item.get("changed"),
            }
            related_paragraphs = item.get("related_infos", {}).get("paragraph", [])
            content = f"{title}\r\n{'\r\n'.join(related_paragraphs)}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs, list(all_diplomas_names)

    def process_domains(self, data: list[dict]) -> list[Document]:
        if not data:
            return []
        docs = []
        all_domains_names = set()
        for item in data:
            item_name = item.get('name')
            all_domains_names.add(item_name)
            metadata = {
                "id": item.get("id"),
                "type": "domaine",
                "name": item_name,
                "changed": item.get("changed"),
            }
            doc = Document(page_content=item_name, metadata=metadata)
            docs.append(doc)
        return docs, list(all_domains_names)
    
    def process_sub_domains(self, data: list[dict]) -> list[Document]:
        if not data:
            return []
        docs = []
        all_subdomains_names = set()
        for item in data:
            item_name = item.get('name')
            all_subdomains_names.add(item_name)
            metadata = {
                "id": item.get("id"),
                "type": "sous-domaine",
                "name": item_name,
                "changed": item.get("changed"),
                "domain_name": item.get("domain_name", item_name),
                "domain_id": item.get("related_ids").get("parent")[0],
            }
            doc = Document(page_content=item_name, metadata=metadata)
            docs.append(doc)
        return docs, list(all_subdomains_names)

    def process_fundings(self, data: list[dict]) -> list[Document]:
        if not data:
            return []
        docs = []
        all_fundings_names = set()
        for item in data:
            all_fundings_names.add(item.get("title"))
            metadata = {
                "id": item.get("id"),
                "type": "financement",
                "name": item.get("title"),
                "changed": item.get("changed"),
            }
            related_paragraphs = item.get("related_infos", {}).get("paragraph", [])
            content = f"{item.get('title', '')}\r\n{'\r\n'.join(related_paragraphs)}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs, list(all_fundings_names)

    def process_jobs(self, data: list[dict], domains) -> list[Document]:
        if not data:
            return []
        docs = []
        all_jobs_names = set()
        for item in data:
            job_title = item.get("title")
            all_jobs_names.add(job_title)
            metadata = {
                "id": item.get("id"),
                "type": "métier",
                "name": job_title,
                "changed": item.get("changed"),
                "rel_ids": self.get_all_ids_as_str(item.get("related_ids", {}))
            }
            domain_id = item.get("related_ids", {}).get("domain", "")
            domain = ''
            if domain_id:
                domain = next((dom.get("name") for dom in domains if dom.get("id") == domain_id), "")
                if not domain:
                    domain = ''
            content = f"Métier : '{metadata['name']}'. {('Domaine : ' + domain) if domain else ''}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)

        #docs.append(Document(page_content= 'Liste complète de tous les métiers couvert par Studi :\n' + ', '.join(all_jobs_names), metadata={"type": "liste_métiers",}))
        return docs, list(all_jobs_names)

    def process_trainings(self, trainings_data: list[dict], trainings_details: dict, existing_docs:list = [], domains_data = None, sub_domains_data = None) -> list[Document]:
        if not trainings_data:
            return []
        docs = []
        all_trainings_titles = set()
        for training_data in trainings_data:
            training_title = training_data.get("title")
            all_trainings_titles.add(training_title)
            related_ids = training_data.get("related_ids", {})
            metadata_common = {
                "id": training_data.get("id"),
                "type": "formation",
                "name": training_title,
                "changed": training_data.get("changed"),
                "rel_ids": self.get_all_ids_as_str(related_ids),
            }            
            sub_domain_id = related_ids.get("domain", "not found")
            subdoms = [sub_domain for sub_domain in sub_domains_data if sub_domain['id'] == sub_domain_id]
            if sub_domain_id == 'not found' or not subdoms or not any(subdoms) or 'parent' not in subdoms[0]['related_ids'] or not subdoms[0]['related_ids']['parent']:
                doms = [domain for domain in domains_data if domain['id'] == sub_domain_id] # check if the sub_domain_id is if fact a domain_id
                if not doms or not any(doms):
                    domain_id = 'not found'
                else:
                    domain_id = doms[0]['id']
            else:
                domain_id = subdoms[0]['related_ids']['parent'][0]

            ids_by_metadata_names = {
                "sub_domain_name": sub_domain_id,
                "domain_name": domain_id,
                "certification_name": related_ids.get("certification", ""),
                # don't work, ids are not all in jobs_ids list: "diplome_names": self.get_list_with_items_as_str(related_ids.get("diploma", [])),
                # don't work, ids are not all in jobs_ids list: "nom_metiers": self.get_list_with_items_as_str(related_ids.get("job", [])),
                # don't work, ids are not in fundings_ids list: "nom_financements": self.get_list_with_items_as_str(related_ids.get("funding", [])),
                # "nom_objectifs": self.as_str(related_ids.get("goal", [])),
            }
            for key, value in ids_by_metadata_names.items():
                if value:
                    is_list = key.endswith('s')
                    if is_list:
                        existing_docs_ids = [doc for doc in existing_docs if doc.metadata.get("id") in value]
                        if len(existing_docs_ids) != len(value):
                            txt.print(f"In process_trainings, on: {key}, {len(value) - len(existing_docs_ids)} docs were not found by its id, on those ids: {value}")
                        if any(existing_docs_ids):
                            metadata_common[key] = ' | '.join(self.get_list_with_items_as_str([doc.metadata.get("name") for doc in existing_docs_ids]))
                    else:
                        existing_docs_ids = [doc for doc in existing_docs if doc.metadata.get("id") == value]
                        #assert len(existing_docs_ids) == 1, f"Multiple or none docs found for: {key} {value}"
                        if any(existing_docs_ids):
                            metadata_common[key] = existing_docs_ids[0].metadata.get("name")

            # Add training URL from details source to metadata
            training_url = ''
            training_detail = trainings_details.get(training_title)
            if training_detail and any(training_detail):
                if 'url' in training_detail:
                    training_url = training_detail['url']
                    metadata_common['url'] = training_url
                if 'academic_level' in training_detail:
                    metadata_common['academic_level'] = training_detail['academic_level']
            else:                    
                txt.print(f"/!\\ Training details not found for: {training_title}")

            # Add 'summary' document with infos from json-api source only
            contents = [f"\n###{self.get_french_section(key)}###\n{Ressource.remove_curly_brackets(value)}" for key, value in training_data.get('attributes', {}).items()]
            content = f"Formation : {training_data.get('title', '')}\nLien vers la page : {training_url}\n{'\n'.join(contents)}"            
            metadata_summary = metadata_common.copy()
            metadata_summary['training_info_type'] = "summary"
            
            # Add training details to doc
            if training_detail and any(training_detail):
                for section_name in training_detail:
                    if section_name not in ['url', 'title']:
                        content_detail = f"###{self.get_french_section(section_name)} de la formation : {training_data.get('title', '')}###\n"
                        content_detail += training_detail[section_name]
                        content += f"\n\n{content_detail}"
                        # metadata_detail = metadata_common.copy()
                        # metadata_detail['training_info_type'] = section_name
                        #docs.append(Document(page_content=content_detail, metadata=metadata_detail))
            docs.append(Document(page_content=content, metadata=metadata_summary))

        #docs.append(Document(page_content= 'Liste complète de toutes les formations proposées par Studi :\n' + ', '.join(all_trainings_titles), metadata={"type": "liste_formations",}))
        return docs, list(all_trainings_titles)
    
    
    section_to_french:dict = None # Singleton containing the static mapping of section names to their french equivalent.
    def get_french_section(self, section_name: str) -> str:
        if not GenerateDocumentsSummariesChunksQuestionsAndMetadata.section_to_french:
            GenerateDocumentsSummariesChunksQuestionsAndMetadata.section_to_french = {
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

        if section_name in GenerateDocumentsSummariesChunksQuestionsAndMetadata.section_to_french:
            return GenerateDocumentsSummariesChunksQuestionsAndMetadata.section_to_french[section_name]
        else:
            raise ValueError(f"Unhandled section name: {section_name} in get_french_section")
    
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