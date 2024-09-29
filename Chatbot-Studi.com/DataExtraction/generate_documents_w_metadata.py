
from common_tools.helpers import JsonHelper
from langchain.schema import Document
from typing import List, Dict

class GenerateDocumentsWithMetadataFromFiles:
    def __init__(self):
        pass
       
    def process_all_data(self, path: str) -> List[Document]:
        all_docs = []

        # Process certifications
        certifications_data = JsonHelper.load_from_json(path + 'certifications.json')
        all_docs.extend(self.process_certifications(certifications_data))

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
        all_docs.extend(self.process_jobs(jobs_data))

        # Process trainings
        trainings_data = JsonHelper.load_from_json(path + 'trainings.json')
        all_docs.extend(self.process_trainings(trainings_data))

        print(f"Total documents created: {len(all_docs)}")
        print(f"---------------------------------")
        print(f"Certifications count: {len(certifications_data)}")
        print(f"Diplomas count: {len(diplomas_data)}")
        print(f"Domains count: {len(domains_data)}")
        print(f"Fundings count: {len(fundings_data)}")
        print(f"Jobs count: {len(jobs_data)}")
        print(f"Trainings count: {len(trainings_data)}")
        print(f"---------------------------------")
        return all_docs

    def process_certifications(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            metadata = {
                "type": "certification",
                "title": item.get("title"),
                "changed": item.get("changed"),
            }
            content = f"{item.get('title', '')}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs

    def process_diplomas(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            metadata = {
                "type": "diplôme",
                "title": item.get("title"),
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
                "type": "domaine",
                "title": item.get("title"),
                "changed": item.get("changed"),
            }
            content = f"{item.get('title', '')}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs

    def process_fundings(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            metadata = {
                "type": "financement",
                "title": item.get("title"),
                "changed": item.get("changed"),
            }
            related_paragraphs = item.get("related_infos", {}).get("paragraph", [])
            content = f"{item.get('title', '')}\r\n{'\r\n'.join(related_paragraphs)}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs

    def process_jobs(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            metadata = {
                "type": "métier",
                "title": item.get("title"),
                "changed": item.get("changed"),
            }
            domain = item.get("related_ids", {}).get("domain", "")
            content = f"{item.get('title', '')}\r\nDomaine/Filière : {domain}"
            doc = Document(page_content=content, metadata=metadata)
            docs.append(doc)
        return docs

    def process_trainings(self, data: List[Dict]) -> List[Document]:
        if not data:
            return []
        docs = []
        for item in data:
            metadata = {
                "type": "formation",
                "title": item.get("title"),
                "changed": item.get("changed"),
            }
            related_ids = item.get("related_ids", {})
            out = {
                "certification_title": related_ids.get("certification", ""),
                "diploma": related_ids.get("diploma", []),
                "domain": related_ids.get("domain", ""),
                "job": related_ids.get("job", []),
                "funding": related_ids.get("funding", []),
            }
            content = f"{item.get('title', '')}\r\n{item.get('field_metatag', '')}"
            doc = Document(page_content=content, metadata={**metadata, **out})
            docs.append(doc)
        return docs