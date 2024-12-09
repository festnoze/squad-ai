from uuid import UUID
import requests
from typing import List, Dict, Union

from client_models.user_query_asking_request_model import UserQueryAskingRequestModel

class ChatbotApiClient:
    def __init__(self, host_uri: str) -> None:
        self.host_uri = host_uri
        self.ingestion_prefix = f"{self.host_uri}/rag/ingestion"
        self.inference_prefix = f"{self.host_uri}/rag/inference"

    def retrieve_all_data(self) -> None:
        requests.post(f"{self.ingestion_prefix}/drupal/data/retrieve")

    def scrape_website_pages(self) -> None:
        requests.post(f"{self.ingestion_prefix}/website/scrape")

    def build_vectorstore(self) -> None:
        requests.post(f"{self.ingestion_prefix}/vectorstore/create")

    def build_summary_vectorstore(self) -> None:
        requests.post(f"{self.ingestion_prefix}/vectorstore/summary/create")

    def generate_ground_truth(self) -> None:
        requests.post(f"{self.ingestion_prefix}/groundtruth/generate")

    def create_new_conversation(self, user_name: str = None) -> UUID:
        params = {"user_name": user_name} if user_name else {}
        resp = requests.get(f"{self.inference_prefix}/query/create", params=params)
        resp.raise_for_status()
        id_str = resp.json().get("id", "")
        return UUID(id_str)

    def rag_query_stream(self, conversation_id:UUID, user_query:str):
        user_query: UserQueryAskingRequestModel = UserQueryAskingRequestModel(conversation_id=conversation_id, user_query_content=user_query, display_waiting_message=False)
        with requests.post(f"{self.inference_prefix}/query/stream", json=user_query.to_json(), stream=True) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
                yield chunk
