import os
import re
import json
import logging
from langchain.schema import Document
#
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.file_helper import file
from common_tools.helpers.json_helper import JsonHelper
from common_tools.helpers.ressource_helper import Ressource
from common_tools.RAG.rag_ingestion_pipeline.summary_and_questions.summary_and_questions_chunks_service import SummaryAndQuestionsChunksService

class GenerateDocumentsAndMetadata:
    logger = logging.getLogger(__name__)
    
    async def build_trainings_docs_summary_chunked_by_questions_async(path, llm_and_fallback: list) -> list[Document]:
        trainings_objects = await GenerateDocumentsAndMetadata.build_trainings_objects_with_summaries_and_chunks_by_questions_async(path, llm_and_fallback)
        trainings_chunks_splitted_by_questions = SummaryAndQuestionsChunksService.build_chunks_splitted_by_questions_from_summaries_and_chunks_by_questions_objects(trainings_objects)
        return trainings_chunks_splitted_by_questions

    async def build_trainings_objects_with_summaries_and_chunks_by_questions_async(path, llm_and_fallback: list):
        trainings_docs_by_sections = GenerateDocumentsAndMetadata.build_trainings_docs_by_sections(path)
        trainings_objects = await SummaryAndQuestionsChunksService.build_summaries_and_chunks_by_questions_objects_from_docs_async(
                                                                            documents=trainings_docs_by_sections, 
                                                                            llm_and_fallback=llm_and_fallback,
                                                                            load_existing_summaries_and_questions_from_file=True,
                                                                            file_path=path, 
                                                                            existing_summaries_and_questions_filename= 'trainings_summaries_chunks_and_questions_objects'
                                                                            )
        return trainings_objects
    
    def build_all_docs_and_trainings(path: str, write_all_names_lists = True) -> list[Document]:
        all_docs_but_trainings = []
        txt.print_with_spinner(f"Build all Langchain documents ...")

        # Process certifiers
        certifiers_data = JsonHelper.load_from_json(os.path.join(path, 'certifiers.json'))
        if not certifiers_data: raise ValueError("No data found. The file 'certifiers.json' might be missing or be empty.")
        certifiers_docs, all_certifiers_names = GenerateDocumentsAndMetadata.process_certifiers(certifiers_data)
        all_docs_but_trainings.extend(certifiers_docs)

        # Process certifications
        certifications_data = JsonHelper.load_from_json(os.path.join(path, 'certifications.json'))
        if not certifications_data: raise ValueError("No data found. The file 'certifications.json' might be missing or be empty.")
        certifications_docs, all_certifications_names = GenerateDocumentsAndMetadata.process_certifications(certifications_data)
        all_docs_but_trainings.extend(certifications_docs)

        # Process diplomas
        diplomas_data = JsonHelper.load_from_json(os.path.join(path, 'diplomas.json'))
        if not diplomas_data: raise ValueError("No data found. The file 'diplomas.json' might be missing or be empty.")
        diplomas_docs, all_diplomas_names = GenerateDocumentsAndMetadata.process_diplomas(diplomas_data)
        all_docs_but_trainings.extend(diplomas_docs)

        # Process domains
        domains_data = JsonHelper.load_from_json(os.path.join(path, 'domains.json'))
        if not domains_data: raise ValueError("No data found. The file 'domains.json' might be missing or be empty.")
        domains_docs, all_domains_names = GenerateDocumentsAndMetadata.process_domains(domains_data)
        all_docs_but_trainings.extend(domains_docs)

        # Process sub-domains
        sub_domains_data = JsonHelper.load_from_json(os.path.join(path, 'subdomains.json'))
        if not sub_domains_data: raise ValueError("No data found. The file 'subdomains.json' might be missing or be empty.")
        sub_domains_docs, all_sub_domains_names = GenerateDocumentsAndMetadata.process_sub_domains(sub_domains_data)
        all_docs_but_trainings.extend(sub_domains_docs)

        # Process fundings
        fundings_data = JsonHelper.load_from_json(os.path.join(path, 'fundings.json'))
        if not fundings_data: raise ValueError("No data found. The file 'fundings.json' might be missing or be empty.")
        fundings_docs, all_fundings_names = GenerateDocumentsAndMetadata.process_fundings(fundings_data)
        all_docs_but_trainings.extend(fundings_docs)

        # Process jobs
        jobs_data = JsonHelper.load_from_json(os.path.join(path, 'jobs.json'))
        if not jobs_data: raise ValueError("No data found. The file 'jobs.json' might be missing or be empty.")
        jobs_docs, all_jobs_names = GenerateDocumentsAndMetadata.process_jobs(jobs_data, domains_data)
        all_docs_but_trainings.extend(jobs_docs)

        # Process trainings
        trainings_docs = GenerateDocumentsAndMetadata.build_trainings_docs_by_sections(path, True, domains_data, sub_domains_data, certifications_data)
        all_trainings_names = GenerateDocumentsAndMetadata.get_all_trainings_names(path)
        if write_all_names_lists:
            path_all = os.path.join(path, 'all')
            file.write_file(all_certifiers_names, os.path.join(path_all, 'all_certifiers_names.json'))
            file.write_file(all_certifications_names, os.path.join(path_all, 'all_certifications_names.json'))
            file.write_file(all_diplomas_names, os.path.join(path_all, 'all_diplomas_names.json'))
            file.write_file(all_domains_names, os.path.join(path_all, 'all_domains_names.json'))
            file.write_file(all_sub_domains_names, os.path.join(path_all, 'all_sub_domains_names.json'))
            file.write_file(all_fundings_names, os.path.join(path_all, 'all_fundings_names.json'))
            file.write_file(all_jobs_names, os.path.join(path_all, 'all_jobs_names.json'))
            file.write_file(all_trainings_names, os.path.join(path_all, 'all_trainings_names.json'))

        txt.stop_spinner_replace_text(f"All Langchain documents built successfully.")
        return all_docs_but_trainings, trainings_docs
    
    def load_trainings_details_from_scraped_dir(path: str) -> dict:
        files_str = file.get_files_paths_and_contents(os.path.join(path, 'scraped/'))
        contents = {}
        for file_path, content_str in files_str.items():
            #filename = file_path.split('/')[-1].split('.')[0]
            content = json.loads(content_str)
            contents[content['title']] = content
        return contents

    def process_certifiers(data: list[dict]) -> tuple[list[Document], list[str]]:
        if not data:
            return []
        all_certifiers_names = set()
        docs = []
        for item in data:
            item_name = item.get('name')
            all_certifiers_names.add(item_name)
            metadata = {
                "doc_id": item.get("id"),
                "type": "certifieur",
                "name": item_name,
                "changed": item.get("changed"),
            }
            doc = Document(page_content=item_name, metadata=metadata)
            docs.append(doc)
        return docs, list(all_certifiers_names)
    
    def process_certifications(data: list[dict]) -> tuple[list[Document], list[str]]:
        if not data:
            return []
        all_certifications_names = set()
        docs = []
        for item in data:
            item_name = item.get('name')
            all_certifications_names.add(item_name)
            metadata = {
                "doc_id": item.get("id"),
                "type": "certification",
                "name": item_name,
                "changed": item.get("changed"),
            }
            doc = Document(page_content=item_name, metadata=metadata)
            docs.append(doc)
        return docs, list(all_certifications_names)

    def process_diplomas(data: list[dict]) -> tuple[list[Document], list[str]]:
        if not data:
            return []
        docs = []
        all_diplomas_names = set()
        for item in data:
            title = item.get("title", '')
            title = re.sub(r'\(.*?\)', '', title).replace("\n", " ").replace(" ?", "").replace("Nos formations en ligne ", "").replace(" en ligne", "").replace("niveau", "").replace("Qu’est-ce qu’un ", "").replace(" +", "+").replace("Nos ", "").replace(" by Studi", "").strip()
            all_diplomas_names.add(title)
            metadata = {
                "doc_id": item.get("id"),
                "type": "diplôme",
                "name": item.get("title"),
                "changed": item.get("changed"),
            }
            related_paragraphs = item.get("related_infos", {}).get("paragraph", [])
            content = f"{title}\r\n{'\r\n'.join(related_paragraphs)}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)

        # Add extra diploma names (use of: academic level and admission level)
        all_diplomas_names.add("pre-graduate")
        all_diplomas_names.add("pregraduate")
        all_diplomas_names.add("master")
        all_diplomas_names.add("MBA")
        all_diplomas_names.add("aucun")
        return docs, list(all_diplomas_names)

    def process_domains(data: list[dict]) -> tuple[list[Document], list[str]]:
        if not data:
            return []
        docs = []
        all_domains_names = set()
        for item in data:
            item_name = item.get('name')
            all_domains_names.add(item_name)
            metadata = {
                "doc_id": item.get("id"),
                "type": "domaine",
                "name": item_name,
                "changed": item.get("changed"),
            }
            doc = Document(page_content=item_name, metadata=metadata)
            docs.append(doc)
        return docs, list(all_domains_names)
    
    def process_sub_domains(data: list[dict]) -> tuple[list[Document], list[str]]:
        if not data:
            return []
        docs = []
        all_subdomains_names = set()
        for item in data:
            item_name = item.get('name')
            all_subdomains_names.add(item_name)
            metadata = {
                "doc_id": item.get("id"),
                "type": "sous-domaine",
                "name": item_name,
                "changed": item.get("changed"),
                "domain_name": item.get("domain_name", item_name),
                "domain_id": item.get("related_ids").get("parent")[0],
            }
            doc = Document(page_content=item_name, metadata=metadata)
            docs.append(doc)
        return docs, list(all_subdomains_names)

    def process_fundings(data: list[dict]) -> tuple[list[Document], list[str]]:
        if not data:
            return []
        docs = []
        all_fundings_names = set()
        for item in data:
            all_fundings_names.add(item.get("title"))
            metadata = {
                "doc_id": item.get("id"),
                "type": "financement",
                "name": item.get("title"),
                "changed": item.get("changed"),
            }
            related_paragraphs = item.get("related_infos", {}).get("paragraph", [])
            content = f"{item.get('title', '')}\r\n{'\r\n'.join(related_paragraphs)}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs, list(all_fundings_names)

    def process_jobs(data: list[dict], domains) -> tuple[list[Document], list[str]]:
        if not data:
            return []
        docs = []
        all_jobs_names = set()
        for item in data:
            job_title = item.get("title")
            all_jobs_names.add(job_title)
            metadata = {
                "doc_id": item.get("id"),
                "type": "métier",
                "name": job_title,
                "changed": item.get("changed"),
                "rel_ids": GenerateDocumentsAndMetadata.get_all_ids_as_str(item.get("related_ids", {}))
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

    def get_all_trainings_names(path: str) -> list[str]:
        trainings_data = JsonHelper.load_from_json(os.path.join(path, 'trainings.json'))
        all_trainings_names = set()
        for training_data in trainings_data:
            all_trainings_names.add(training_data.get("title"))
        return list(all_trainings_names)
        
    def build_trainings_docs_by_sections(path:str, add_training_summary:bool = True, domains_data = None, sub_domains_data = None, certifications_data = None) -> list[Document]:
        if not domains_data: domains_data = JsonHelper.load_from_json(os.path.join(path, 'domains.json'))
        if not sub_domains_data: sub_domains_data = JsonHelper.load_from_json(os.path.join(path, 'subdomains.json'))
        if not certifications_data: certifications_data = JsonHelper.load_from_json(os.path.join(path, 'certifications.json'))
        trainings_data_from_drupal = JsonHelper.load_from_json(os.path.join(path, 'trainings.json'))
        if not trainings_data_from_drupal: raise ValueError("No trainings data found. The file 'trainings.json' might be missing or be empty.")
        trainings_details_from_scraping = GenerateDocumentsAndMetadata.load_trainings_details_from_scraped_dir(path)
        if not trainings_details_from_scraping: raise ValueError("No trainings details found. The 'scraped' directory might be missing or be empty.")
        
        unfound_in_scraped_trainings_count = 0
        unfound_in_drupal_trainings_count = 0
        unfound_domain_or_certif_count = 0
        docs = []
        removed_sections_names: set = set()

        # Check first that all scraped trainings from Studi.com are present in the Drupal data
        for training_title in trainings_details_from_scraping.keys():
            training_data_drupal = next((training for training in trainings_data_from_drupal if training.get("title") == training_title), None)
            if not training_data_drupal:
                unfound_in_drupal_trainings_count += 1
                GenerateDocumentsAndMetadata.logger.warning(f"!!! N°{unfound_in_drupal_trainings_count} unfound training from scraped data: '{training_title}', doesn't exists onto the Drupal data.")

        for training_data_drupal in trainings_data_from_drupal:
            training_title = training_data_drupal.get("title")
            training_detail = trainings_details_from_scraping.get(training_title)
            # Only keep the training from Drupal if it's also present onto the website
            if not training_detail:
                unfound_in_scraped_trainings_count += 1                    
                GenerateDocumentsAndMetadata.logger.warning(f"!!! N°{unfound_in_scraped_trainings_count} unfound training from Drupal: '{training_title}', doesn't exists onto the website (or at least into the scraped data).")
                continue

            related_ids = training_data_drupal.get("related_ids", {})
            metadata_common = {
                "doc_id": training_data_drupal.get("id"),
                "type": "formation",
                "name": training_title,
                "changed": training_data_drupal.get("changed"),
                "rel_ids": GenerateDocumentsAndMetadata.get_all_ids_as_str(related_ids),
            }            
            
            # Verify domain and sub-domain from their ids
            domain_id = related_ids.get("domain", None)
            sub_domain_id = None
            if domain_id:
                # Search for domain with domain_id
                doms = [domain for domain in domains_data if domain["id"] == domain_id]
                # If unfound "domain_id", look if it rather is a sub_domain_id
                if not doms:
                    sub_domains = [sub_domain for sub_domain in sub_domains_data if sub_domain["id"] == domain_id]
                    if not sub_domains:
                        raise ValueError(f"Domain or Sub-domain not found with id: {domain_id}")
                    sub_domain_id = sub_domains[0]["id"]
                    # Deduce the domain from the sub-domain parent
                    if 'parent' in sub_domains[0]['related_ids'] and sub_domains[0]['related_ids']['parent']:
                        domain_id = sub_domains[0]['related_ids']['parent'][0]

            certification_id = related_ids.get("certification", None)

            if domain_id:
                metadata_common["domain_name"] = next((dom.get("name") for dom in domains_data if dom.get("id") == domain_id), "")
            else:
                unfound_domain_or_certif_count += 1
                GenerateDocumentsAndMetadata.logger.warning(f"## N°{unfound_domain_or_certif_count} unfound 'domain'. For: {training_title}")
            
            if sub_domain_id:
                metadata_common["sub_domain_name"] = next((sub_dom.get("name") for sub_dom in sub_domains_data if sub_dom.get("id") == sub_domain_id), "")
            else:
                unfound_domain_or_certif_count += 1
                GenerateDocumentsAndMetadata.logger.warning(f"## N°{unfound_domain_or_certif_count} unfound 'sub-domain'. For: {training_title}")
            
            if certification_id:
                metadata_common["certification_name"] = next((cert.get("name") for cert in certifications_data if cert.get("id") == certification_id), "")
            else:
                unfound_domain_or_certif_count += 1
                GenerateDocumentsAndMetadata.logger.warning(f"## N°{unfound_domain_or_certif_count} unfound 'certification'. For: {training_title}")

            # Add training URL from details source to metadata
            training_url = ''
            
            if 'url' in training_detail:
                training_url = training_detail['url']
                metadata_common['url'] = training_url
            if 'academic_level' in training_detail:
                metadata_common['academic_level'] = training_detail['academic_level']
            else:
                metadata_common['academic_level'] = 'aucun'

            # Add 'summary' document with all attributs infos from json-api source only
            if add_training_summary:
                contents = [f"\n###{GenerateDocumentsAndMetadata.get_french_section(key)}###\n{Ressource.remove_curly_brackets(value)}" for key, value in training_data_drupal.get('attributes', {}).items()]  
                content = f"Formation : {training_data_drupal.get('title', '')}\nLien vers la page : {training_url}\n{'\n'.join(contents)}"            
                metadata_summary = metadata_common.copy()
                metadata_summary['training_info_type'] = "summary"
                docs.append(Document(page_content=content, metadata=metadata_summary))
            
            # Add all training sections as separate docs
            if training_detail and any(training_detail):
                for section_name in training_detail:
                    #TODO: Possible to add more sections: 'metiers' and 'academic_level' (also add to metadata description in this case)
                    if section_name in ['summary', 'bref', 'header-training', 'programme', 'cards-diploma', 'methode', 'modalites', 'financement', 'simulation', 'metiers', 'academic_level']:
                        content = f"###{GenerateDocumentsAndMetadata.get_french_section(section_name)} de la formation : {training_data_drupal.get('title', '')}###\n{training_detail[section_name]}"
                        metadata_detail = metadata_common.copy()
                        metadata_detail['training_info_type'] = section_name
                        docs.append(Document(page_content=content, metadata=metadata_detail))
                    else:
                        removed_sections_names.add(section_name)

        if unfound_in_scraped_trainings_count > 0:
            GenerateDocumentsAndMetadata.logger.warning(f"!!! Total : {unfound_in_scraped_trainings_count} trainings from json-api Drupal were not found on the scraped website data.")
        
        #docs.append(Document(page_content= 'Liste complète de toutes les formations proposées par Studi :\n' + ', '.join(all_trainings_titles), metadata={"type": "liste_formations",}))
        return docs
    
    def get_french_section(section_name: str) -> str:
        if not section_name in GenerateDocumentsAndMetadata.section_to_french:
            print(f"<>>>>> Unhandled section name: {section_name} in {GenerateDocumentsAndMetadata.get_french_section.__name__} <<<<<<>")
            return section_name.replace('_', ' ').capitalize()
        return GenerateDocumentsAndMetadata.section_to_french[section_name]

    section_to_french = {
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
                'goals': "Objectifs",
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
                'code_rncp': "Code RNCP",
                # Added 04/2025
                'color_text': "Texte en couleur",
            }

    def get_all_ids_as_str(related_ids):
        all_ids = []
        for key, value in related_ids.items():
            if isinstance(value, list):
                all_ids.extend(value)
            elif isinstance(value, str):
                all_ids.append(value)
        all_ids_str = ",".join(all_ids)
        return all_ids_str