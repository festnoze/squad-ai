
import json
import os
import re
from typing import List, Dict
import uuid
from langchain.schema import Document
#
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.file_helper import file
from common_tools.helpers.json_helper import JsonHelper
from common_tools.helpers.ressource_helper import Ressource

class GenerateDocumentsAndMetadata:
    
    def load_all_docs_as_json(path: str, write_all_lists = True) -> List[Document]:
        all_docs = []
        txt.print_with_spinner(f"Build all Langchain documents ...")

        # Process certifiers
        certifiers_data = JsonHelper.load_from_json(os.path.join(path, 'certifiers.json'))
        certifiers_docs, all_certifiers_names = GenerateDocumentsAndMetadata.process_certifiers(certifiers_data)
        all_docs.extend(certifiers_docs)

        # Process certifications
        certifications_data = JsonHelper.load_from_json(os.path.join(path, 'certifications.json'))
        certifications_docs, all_certifications_names = GenerateDocumentsAndMetadata.process_certifications(certifications_data)
        all_docs.extend(certifications_docs)

        # Process diplomas
        diplomas_data = JsonHelper.load_from_json(os.path.join(path, 'diplomas.json'))
        diplomas_docs, all_diplomas_names = GenerateDocumentsAndMetadata.process_diplomas(diplomas_data)
        all_docs.extend(diplomas_docs)

        # Process domains
        domains_data = JsonHelper.load_from_json(os.path.join(path, 'domains.json'))
        domains_docs, all_domains_names = GenerateDocumentsAndMetadata.process_domains(domains_data)
        all_docs.extend(domains_docs)

        # Process sub-domains
        sub_domains_data = JsonHelper.load_from_json(os.path.join(path, 'subdomains.json'))
        sub_domains_docs, all_sub_domains_names = GenerateDocumentsAndMetadata.process_sub_domains(sub_domains_data)
        all_docs.extend(sub_domains_docs)

        # Process fundings
        fundings_data = JsonHelper.load_from_json(os.path.join(path, 'fundings.json'))
        fundings_docs, all_fundings_names = GenerateDocumentsAndMetadata.process_fundings(fundings_data)
        all_docs.extend(fundings_docs)

        # Process jobs
        jobs_data = JsonHelper.load_from_json(os.path.join(path, 'jobs.json'))
        jobs_docs, all_jobs_names = GenerateDocumentsAndMetadata.process_jobs(jobs_data, domains_data)
        all_docs.extend(jobs_docs)

        # Process trainings
        trainings_data = JsonHelper.load_from_json(os.path.join(path, 'trainings.json'))
        trainings_details = GenerateDocumentsAndMetadata.load_trainings_details_as_json(path)
        trainings_docs, all_trainings_names = GenerateDocumentsAndMetadata.process_trainings(trainings_data, trainings_details, all_docs, domains_data, sub_domains_data)
        all_docs.extend(trainings_docs)

        if write_all_lists:
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
        txt.print(f"Certifiers count: {len(certifiers_data)}")
        txt.print(f"Certifications count: {len(certifiers_data)}")
        txt.print(f"Diplomas count: {len(diplomas_data)}")
        txt.print(f"Domains count: {len(domains_data)}")
        txt.print(f"Fundings count: {len(fundings_data)}")
        txt.print(f"Jobs count: {len(jobs_data)}")
        txt.print(f"Trainings count: {len(trainings_data)}")
        txt.print(f"Trainings docs count: {len(trainings_docs)}")
        txt.print(f"--------------------------------")
        txt.print(f"Total documents created: {len(all_docs)}")
        return all_docs
    
    def load_trainings_details_as_json(path: str) -> dict:
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


    def process_certifiers(data: List[Dict]) -> List[Document]:
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
    
    def process_certifications(data: List[Dict]) -> List[Document]:
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

    def process_diplomas(data: List[Dict]) -> List[Document]:
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
        return docs, list(all_diplomas_names)

    def process_domains(data: List[Dict]) -> List[Document]:
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
    
    def process_sub_domains(data: List[Dict]) -> List[Document]:
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

    def process_fundings(data: List[Dict]) -> List[Document]:
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

    def process_jobs(data: List[Dict], domains) -> List[Document]:
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

    def process_trainings(trainings_data: List[Dict], trainings_details: dict, existing_docs:list = [], domains_data = None, sub_domains_data = None) -> List[Document]:
        if not trainings_data: return []
        docs = []
        all_trainings_titles = set()
        
        for training_data in trainings_data:
            training_title = training_data.get("title")
            all_trainings_titles.add(training_title)
            related_ids = training_data.get("related_ids", {})
            metadata_common = {
                "doc_id": training_data.get("id"),
                "type": "formation",
                "name": training_title,
                "changed": training_data.get("changed"),
                "rel_ids": GenerateDocumentsAndMetadata.get_all_ids_as_str(related_ids),
            }            
            sub_domain_id = related_ids.get("domain", "not found")
            subdoms = [sub_domain for sub_domain in sub_domains_data if sub_domain["id"] == sub_domain_id]
            if sub_domain_id == 'not found' or not subdoms or not any(subdoms) or 'parent' not in subdoms[0]['related_ids'] or not subdoms[0]['related_ids']['parent']:
                doms = [domain for domain in domains_data if domain["id"] == sub_domain_id] # check if the sub_domain_id is if fact a domain_id
                if not doms or not any(doms):
                    domain_id = 'not found'
                else:
                    domain_id = doms[0]["id"]
            else:
                domain_id = subdoms[0]['related_ids']['parent'][0]

            ids_by_metadata_names = {
                "sub_domain_name": sub_domain_id,
                "domain_name": domain_id,
                "certification_name": related_ids.get("certification", ""),
                # don't work, ids are not all in jobs_ids list: "diplome_names": GenerateDocumentsAndMetadata.get_list_with_items_as_str(related_ids.get("diploma", [])),
                # don't work, ids are not all in jobs_ids list: "nom_metiers": GenerateDocumentsAndMetadata.get_list_with_items_as_str(related_ids.get("job", [])),
                # don't work, ids are not in fundings_ids list: "nom_financements": GenerateDocumentsAndMetadata.get_list_with_items_as_str(related_ids.get("funding", [])),
                # "nom_objectifs": GenerateDocumentsAndMetadata.as_str(related_ids.get("goal", [])),
            }
            for key, value in ids_by_metadata_names.items():
                if value:
                    is_list = key.endswith('s')
                    if is_list:
                        existing_docs_ids = [doc for doc in existing_docs if doc.metadata.get("id") in value]
                        if len(existing_docs_ids) != len(value):
                            txt.print(f"In process_trainings, on: {key}, {len(value) - len(existing_docs_ids)} docs were not found by its id, on those ids: {value}")
                        if any(existing_docs_ids):
                            metadata_common[key] = ' | '.join(GenerateDocumentsAndMetadata.get_list_with_items_as_str([doc.metadata.get("name") for doc in existing_docs_ids]))
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
            contents = [f"\n##{GenerateDocumentsAndMetadata.get_french_section(key)}##\n{Ressource.remove_curly_brackets(value)}" for key, value in training_data.get('attributes', {}).items()]
            
            content = f"Formation : {training_data.get('title', '')}\nLien vers la page : {training_url}\n{'\n'.join(contents)}"            
            metadata_summary = metadata_common.copy()
            metadata_summary['training_info_type'] = "summary"
            docs.append(Document(page_content=content, metadata=metadata_summary))
            
            # Add training details to docs
            if training_detail and any(training_detail):
                for section_name in training_detail:
                    if section_name not in ['url', 'title']:
                        content = f"##{GenerateDocumentsAndMetadata.get_french_section(section_name)} de la formation : {training_data.get('title', '')}##\n"
                        content += training_detail[section_name]
                        metadata_detail = metadata_common.copy()
                        metadata_detail['training_info_type'] = section_name
                        docs.append(Document(page_content=content, metadata=metadata_detail))

        #docs.append(Document(page_content= 'Liste complète de toutes les formations proposées par Studi :\n' + ', '.join(all_trainings_titles), metadata={"type": "liste_formations",}))
        return docs, list(all_trainings_titles)
    
    def get_french_section(section: str) -> str:
        if section == 'title':
            return "Titre"
        elif section == 'academic_level':
            return "Niveau académique"
        elif section == 'content':
            return "Contenu"
        elif section == 'certification':
            return "Certification"
        elif section == 'diploma':
            return "Diplôme"
        elif section == 'domain':
            return "Domaine"
        elif section == 'job' or section == 'metiers':
            return "Métiers"
        elif section == 'funding':
            return "Financements"
        elif section == 'goal':
            return "Objectifs"
        elif section == 'summary':
            return "Résumé"
        elif section == 'header-training':
            return "Informations générales"
        elif section == 'bref':
            return "Description en bref"
        elif section == 'cards-diploma':
            return "Diplômes obtenus"
        elif section == 'programme':
            return "Programme"
        elif section == 'financement':
            return "Financements possibles"
        elif section == 'methode':
            return "Méthode d'apprentissage Studi"
        elif section == 'modalites':
            return "Modalités"
        elif section == 'simulation':
            return "Simulation de formation"
        elif section == 'accessibility':
            return "Accessibilité"
        elif section == 'accompaniment':
            return "'Accompagnement"
        elif section == 'certif':
            return "'Certifications"
        else:
            return section
    
    def get_list_with_items_as_str(lst: list):
        if not lst:
            return []
        return [str(uid) for uid in lst]
    
    def get_all_ids_as_str(related_ids):
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