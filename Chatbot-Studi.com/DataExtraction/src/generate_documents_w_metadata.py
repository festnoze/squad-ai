
import json
from common_tools.helpers.json_helper import JsonHelper
from langchain.schema import Document
from typing import List, Dict
#
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.file_helper import file

class GenerateDocumentsWithMetadataFromFiles:
    def __init__(self):
        pass
       
    def load_all_docs_as_json(self, path: str, write_all_lists = True) -> List[Document]:
        all_docs = []
        txt.print_with_spinner(f"Build all Langchain documents ...")

        # Process certifiers
        certifiers_data = JsonHelper.load_from_json(path + 'certifiers.json')
        certifiers_docs, all_certifiers_names = self.process_certifiers(certifiers_data)
        all_docs.extend(certifiers_docs)

        # Process certifications
        certifications_data = JsonHelper.load_from_json(path + 'certifications.json')
        certifications_docs, all_certifications_names = self.process_certifications(certifications_data)
        all_docs.extend(certifications_docs)

        # Process diplomas
        diplomas_data = JsonHelper.load_from_json(path + 'diplomas.json')
        diplomas_docs, all_diplomas_names = self.process_diplomas(diplomas_data)
        all_docs.extend(diplomas_docs)

        # Process domains
        domains_data = JsonHelper.load_from_json(path + 'domains.json')
        domains_docs, all_domains_names = self.process_domains(domains_data)
        all_docs.extend(domains_docs)

        # Process fundings
        fundings_data = JsonHelper.load_from_json(path + 'fundings.json')
        fundings_docs, all_fundings_names = self.process_fundings(fundings_data)
        all_docs.extend(fundings_docs)

        # Process jobs
        jobs_data = JsonHelper.load_from_json(path + 'jobs.json')
        jobs_docs, all_jobs_names = self.process_jobs(jobs_data, domains_data)
        all_docs.extend(jobs_docs)

        # Process trainings
        trainings_data = JsonHelper.load_from_json(path + 'trainings.json')
        trainings_details = self.load_trainings_details_as_json(path)
        trainings_docs, all_trainings_names = self.process_trainings(trainings_data, trainings_details, all_docs)
        all_docs.extend(trainings_docs)

        if write_all_lists:
            file.write_file(all_certifiers_names, path + 'all/' + 'all_certifiers_names.json')
            file.write_file(all_certifications_names, path + 'all/' + 'all_certifications_names.json')
            file.write_file(all_diplomas_names, path + 'all/' + 'all_diplomas_names.json')
            file.write_file(all_domains_names, path + 'all/' + 'all_domains_names.json')
            file.write_file(all_fundings_names, path + 'all/' + 'all_fundings_names.json')
            file.write_file(all_jobs_names, path + 'all/' + 'all_jobs_names.json')
            file.write_file(all_trainings_names, path + 'all/' + 'all_trainings_names.json')

        txt.stop_spinner_replace_text(f"All Langchain documents built successfully.")
        txt.print(f"Certifiers count: {len(certifiers_data)}")
        txt.print(f"Certifications count: {len(certifiers_data)}")
        txt.print(f"Diplomas count: {len(diplomas_data)}")
        txt.print(f"Domains count: {len(domains_data)}")
        txt.print(f"Fundings count: {len(fundings_data)}")
        txt.print(f"Jobs count: {len(jobs_data)}")
        txt.print(f"Trainings count: {len(trainings_data)}")
        txt.print(f"---------------------")
        txt.print(f"Total documents created: {len(all_docs)}")
        return all_docs
    
    def load_trainings_details_as_json(self, path: str) -> dict:
        files_str = file.get_files_paths_and_contents(path + 'scraped/')
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


    def process_certifiers(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        all_certifiers_names = []
        docs = []
        for item in data:
            all_certifiers_names.append(item.get("name"))
            metadata = {
                "id": item.get("id"),
                "type": "certifieur",
                "name": item.get("name"),
                "changed": item.get("changed"),
            }
            content = f"{item.get('name', '')}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs, all_certifiers_names
    
    def process_certifications(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        all_certifications_names = []
        docs = []
        for item in data:
            all_certifications_names.append(item.get("name"))
            metadata = {
                "id": item.get("id"),
                "type": "certification",
                "name": item.get("name"),
                "changed": item.get("changed"),
            }
            content = f"{item.get('name', '')}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs, all_certifications_names

    def process_diplomas(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        docs = []
        all_diplomas_names = []
        for item in data:
            all_diplomas_names.append(item.get("title"))
            metadata = {
                "id": item.get("id"),
                "type": "diplôme",
                "name": item.get("title"),
                "changed": item.get("changed"),
            }
            related_paragraphs = item.get("related_infos", {}).get("paragraph", [])
            content = f"{item.get('title', '')}\r\n{'\r\n'.join(related_paragraphs)}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs, all_diplomas_names

    def process_domains(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        docs = []
        all_domains_names = []
        for item in data:
            all_domains_names.append(item.get("name"))
            metadata = {
                "id": item.get("id"),
                "type": "domaine",
                "name": item.get("name"),
                "changed": item.get("changed"),
            }
            content = f"{item.get('name', '')}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs, all_domains_names

    def process_fundings(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        docs = []
        all_fundings_names = []
        for item in data:
            all_fundings_names.append(item.get("title"))
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
        return docs, all_fundings_names

    def process_jobs(self, data: List[Dict], domains) -> List[Document]:
        if not data:
            return []
        docs = []
        all_jobs_names = []
        for item in data:
            job_title = item.get("title")
            all_jobs_names.append(job_title)
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
        return docs, all_jobs_names

    def process_trainings(self, data: List[Dict], trainings_details: dict, existing_docs:list = []) -> List[Document]:
        if not data:
            return []
        docs = []
        all_trainings_titles = []
        for item in data:
            training_title = item.get("title")
            all_trainings_titles.append(training_title)
            related_ids = item.get("related_ids", {})
            metadata_common = {
                "id": item.get("id"),
                "type": "formation",
                "name": training_title,
                "changed": item.get("changed"),
                "rel_ids": self.get_all_ids_as_str(related_ids),
            }

            related_ids = {
                "nom_domaine": related_ids.get("domain", ""),
                "nom_certification": related_ids.get("certification", ""),
                # "nom_diplomes": self.as_str(related_ids.get("diploma", [])),
                # "nom_metiers": self.as_str(related_ids.get("job", [])),
                # "nom_financements": self.as_str(related_ids.get("funding", [])),
                # "nom_objectifs": self.as_str(related_ids.get("goal", [])),
            }

            for key, value in related_ids.items():
                if value:
                    is_list = key.endswith('s')
                    if is_list:
                        existing_docs_ids = [doc for doc in existing_docs if doc.metadata.get("id") in value]
                        #assert len(existing_docs_ids) == len(value), f"At least one of the docs were not found by its id, on: {key} {value}"
                        if any(existing_docs_ids):
                            metadata_common[key] = self.as_str([doc.metadata.get("name") for doc in existing_docs_ids])
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
            else:                    
                txt.print(f"/!\\ Training details not found for: {training_title}")

            # Add 'summary' document with infos from json-api source only
            contents = [value for key, value in item.get('attributes', {}).items()]
            content = f"Formation : {item.get('title', '')}\nLien vers la page : {training_url}\n{'\n'.join(contents)}"            
            metadata_summary = metadata_common.copy()
            metadata_summary['training_info_type'] = "summary"
            docs.append(Document(page_content=content, metadata=metadata_summary))
            
            # Add training details to docs
            if training_detail and any(training_detail):
                for section_name in training_detail:
                    if section_name not in ['url', 'title']:
                        content = f"##{self.get_french_section(section_name)} de la formation : {item.get('title', '')}##\n"
                        content += training_detail[section_name]
                        metadata_detail = metadata_common.copy()
                        metadata_detail['training_info_type'] = section_name
                        docs.append(Document(page_content=content, metadata=metadata_detail))

        #docs.append(Document(page_content= 'Liste complète de toutes les formations proposées par Studi :\n' + ', '.join(all_trainings_titles), metadata={"type": "liste_formations",}))
        return docs, all_trainings_titles
    
    def get_french_section(self, section: str) -> str:
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
        else:
            raise ValueError(f"Unhandled section name: {section} in get_french_section")
    
    def as_str(self, lst: list):
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