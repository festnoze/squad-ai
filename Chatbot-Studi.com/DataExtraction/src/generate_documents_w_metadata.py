
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
       
    def load_all_docs_as_json(self, path: str) -> List[Document]:
        all_docs = []
        txt.print_with_spinner(f"Build all Langchain documents ...")

        # Process certifiers
        certifiers_data = JsonHelper.load_from_json(path + 'certifiers.json')
        all_docs.extend(self.process_certifiers(certifiers_data))

        # Process certifications
        certifiers_data = JsonHelper.load_from_json(path + 'certifications.json')
        all_docs.extend(self.process_certifications(certifiers_data))

        # Process diplomas
        diplomas_data = JsonHelper.load_from_json(path + 'diplomas.json')
        all_docs.extend(self.process_diplomas(diplomas_data))

        # Process domains
        domains_data = JsonHelper.load_from_json(path + 'domains.json')
        all_docs.extend(self.process_domains(domains_data))

        # Process fundings
        fundings_data = JsonHelper.load_from_json(path + 'fundings.json')
        all_docs.extend(self.process_fundings(fundings_data))

        # Process jobs
        jobs_data = JsonHelper.load_from_json(path + 'jobs.json')
        all_docs.extend(self.process_jobs(jobs_data, domains_data))

        # Process trainings
        trainings_details = self.load_trainings_details_as_json(path)
        trainings_data = JsonHelper.load_from_json(path + 'trainings.json')
        all_docs.extend(self.process_trainings(trainings_data, trainings_details))

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
        docs = []
        for item in data:
            metadata = {
                "id": item.get("id"),
                "type": "certifieur",
                "name": item.get("name"),
                "changed": item.get("changed"),
            }
            content = f"{item.get('name', '')}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs
    
    def process_certifications(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            metadata = {
                "id": item.get("id"),
                "type": "certification",
                "name": item.get("name"),
                "changed": item.get("changed"),
            }
            content = f"{item.get('name', '')}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs

    def process_diplomas(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        docs = []
        for item in data:
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
        return docs

    def process_domains(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            metadata = {
                "id": item.get("id"),
                "type": "domaine",
                "name": item.get("name"),
                "changed": item.get("changed"),
            }
            content = f"{item.get('name', '')}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs

    def process_fundings(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        docs = []
        for item in data:
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
        return docs

    def process_jobs(self, data: List[Dict], domains) -> List[Document]:
        if not data:
            return []
        docs = []
        all_jobs_titles = []
        for item in data:
            job_title = item.get("title")
            all_jobs_titles.append(job_title)
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
            content = f"Métier : '{metadata['name']}'. {('\r\nAppartient au domaine (ou filière) : ' + domain) if domain else ''}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)

        docs.append(Document(page_content= 'Liste complète de tous les métiers couvert par Studi :\n' + ', '.join(all_jobs_titles), metadata={"type": "liste_métiers",}))
        return docs

    def process_trainings(self, data: List[Dict], trainings_details: dict) -> List[Document]:
        if not data:
            return []
        docs = []
        all_trainings_titles = []
        for item in data:
            training_title = item.get("title")
            all_trainings_titles.append(training_title)

            metadata_common = {
                "id": item.get("id"),
                "type": "formation",
                "name": training_title,
                "changed": item.get("changed"),
                "rel_ids": self.get_all_ids_as_str(item.get("related_ids", {})),
            }

            # ext_ids = {
            #     "certification_id": related_ids.get("certification", ""),
            #     "diploma_ids": self.as_str(related_ids.get("diploma", [])),
            #     "domain_id": related_ids.get("domain", ""),
            #     "job_ids": self.as_str(related_ids.get("job", [])),
            #     "funding_ids": self.as_str(related_ids.get("funding", [])),
            #     "goal_ids": self.as_str(related_ids.get("goal", [])),
            # }

            # Add training URL from details source
            training_url = ''
            training_url_str = ''
            training_detail = trainings_details.get(training_title)
            if training_detail and any(training_detail):
                if 'url' in training_detail:
                    training_url = training_detail['url']
                    training_url_str = f"Lien vers la formation : {training_url}\n" 
            else:                    
                txt.print(f"/!\\ Training details not found for: {training_title}")
            
            # contents = [value for key, value in item.get('attributes', {}).items()]
            # content = f"Formation : {item.get('title', '')}\n{training_url_str}{'\n'.join(contents)}"            
            # metadata_summary = metadata_common.copy()
            # metadata_summary['training_info_type'] = "summary"
            # docs.append(Document(page_content=content, metadata=metadata_summary))
            
            # Add training details to docs
            if training_detail and any(training_detail):
                for section_name in training_detail:
                    content = f"##{self.get_french_section(section_name)} de la formation : {item.get('title', '')}##\n"
                    content += training_detail[section_name]
                    metadata_detail = metadata_common.copy()
                    metadata_detail['training_info_type'] = section_name
                    docs.append(Document(page_content=content, metadata=metadata_detail))

        docs.append(Document(page_content= 'Liste complète de toutes les formations proposées par Studi :\n' + ', '.join(all_trainings_titles), metadata={"type": "liste_formations",}))
        return docs
    
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
        elif section == 'job':
            return "Métiers"
        elif section == 'funding':
            return "Financements"
        elif section == 'goal':
            return "Objectifs"
        return
    
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