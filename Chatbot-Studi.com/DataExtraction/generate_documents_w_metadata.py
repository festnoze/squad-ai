
from common_tools.helpers import JsonHelper
from langchain.schema import Document
from typing import List, Dict
#
from common_tools.helpers import txt

class GenerateDocumentsWithMetadataFromFiles:
    def __init__(self):
        pass
       
    def process_all_data(self, path: str) -> List[Document]:
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
        trainings_data = JsonHelper.load_from_json(path + 'trainings.json')
        all_docs.extend(self.process_trainings(trainings_data))

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
        for item in data:
            metadata = {
                "id": item.get("id"),
                "type": "métier",
                "name": item.get("title"),
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
        return docs

    def process_trainings(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            metadata = {
                "id": item.get("id"),
                "type": "formation",
                "name": item.get("title"),
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
            content = f"{item.get('title', '')}\r\n{item.get('field_metatag', '')}"
            doc = Document(page_content=content, metadata=metadata)#{**metadata, **ext_ids})
            docs.append(doc)
        return docs
    
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