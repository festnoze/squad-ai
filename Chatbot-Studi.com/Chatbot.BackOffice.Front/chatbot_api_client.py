from uuid import UUID
import requests
from typing import Generator, List, Dict, Union

from client_models.user_query_asking_request_model import UserQueryAskingRequestModel
from client_models.user_request_model import UserRequestModel

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
        requests.post(f"{self.ingestion_prefix}/vectorstore/create/full")

    def build_summary_vectorstore(self) -> None:
        requests.post(f"{self.ingestion_prefix}/vectorstore/create/from-summaries")

    def generate_ground_truth(self) -> None:
        requests.post(f"{self.ingestion_prefix}/groundtruth/generate")

    def create_or_update_user(self, user_request_model: UserRequestModel) -> UUID:
        url = f"{self.inference_prefix}/user/sync"
        headers = {"Content-Type": "application/json"}

        resp = requests.patch(url, json=user_request_model.to_json(), headers=headers)
        if not resp.ok:
            raise requests.exceptions.HTTPError(
                f"Create or update user request failed with status code {resp.status_code}, payload: {resp.text}"
            )
        try:
            data = resp.json()
            user_id = data.get("id", None)
            if not user_id:
                raise ValueError("Invalid response, missing 'Id'.")
            return UUID(user_id)
        except (requests.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Invalid JSON response: {resp.text}") from e

    def create_new_conversation(self, user_id: UUID) -> UUID:
        url = f"{self.inference_prefix}/conversation/create"
        payload = {"user_id": str(user_id), "messages": []}
        headers = {"Content-Type": "application/json"}

        resp = requests.post(url, json=payload, headers=headers)
        if resp.status_code == 429:  # Handle HTTP Error 429 specifically
            raise Exception("New conversations quota exceeded.")
        elif not resp.ok:
            raise requests.exceptions.HTTPError(
                f"Create conversation request failed with status code {resp.status_code}, payload: {resp.text}"
            )

        try:
            data = resp.json()
            conversation_id = data.get("id", None)
            if not conversation_id:
                raise ValueError("Invalid response, missing 'id'.")
            return UUID(conversation_id)
        except (requests.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Invalid JSON response: {resp.text}") from e

    def rag_query_stream(self, user_query_request: UserQueryAskingRequestModel) -> Generator[str, None, None]:
        url = f"{self.inference_prefix}/conversation/ask-question/stream"
        headers = {"Content-Type": "application/json"}

        with requests.post(url, json=user_query_request.to_json(), headers=headers, stream=True) as resp:
            if resp.status_code == 429:  # Handle HTTP Error 429 specifically
                raise Exception("Requests per conversation quota exceeded.")
            elif not resp.ok:
                raise requests.exceptions.HTTPError(
                    f"Answer user query request failed with status code {resp.status_code}, payload: {resp.text}"
                )

            try:
                for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
                    if chunk.strip():  # Only yield non-empty chunks
                        yield chunk
            except Exception as e:
                raise RuntimeError("Error processing streaming response.") from e