import requests
from typing import Generator

class StudiPublicWebsiteClient:
    def __init__(self, base_url: str) -> None:
        self.base_url: str = base_url

    def reinitialize(self) -> None:
        url: str = f"{self.base_url}/rag/inference/reinitialize"
        response: requests.Response = requests.post(url)
        response.raise_for_status()

    def test_all_models(self) -> dict[str, any]:
        url: str = f"{self.base_url}/tests/models/all"
        response: requests.Response = requests.get(url)
        response.raise_for_status()
        return response.json()

    def create_or_retrieve_user(
        self,
        user_id: str,
        user_name: str,
        ip: str,
        user_agent: str,
        platform: str,
        app_version: str,
        os_value: str,
        browser: str,
        is_mobile: bool
    ) -> dict[str, any]:
        url: str = f"{self.base_url}/rag/inference/user/sync"
        payload: dict[str, any] = {
            "user_id": user_id,
            "user_name": user_name,
            "IP": ip,
            "device_info": {
                "user_agent": user_agent,
                "platform": platform,
                "app_version": app_version,
                "os": os_value,
                "browser": browser,
                "is_mobile": is_mobile
            }
        }
        response: requests.Response = requests.patch(url, json=payload)
        response.raise_for_status()
        return response.json()

    def create_new_conversation(
        self,
        user_id: str,
        messages: list[dict[str, str]]
    ) -> dict[str, any]:
        url: str = f"{self.base_url}/rag/inference/conversation/create"
        payload: dict[str, any] = {
            "user_id": user_id,
            "messages": messages
        }
        response: requests.Response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    def rag_query_stream(
        self,
        conversation_id: str,
        user_query_content: str,
        display_waiting_message: bool
    ) -> Generator[str, None, None]:
        url: str = f"{self.base_url}/rag/inference/conversation/ask-question/stream"
        payload: dict[str, any] = {
            "conversation_id": conversation_id,
            "user_query_content": user_query_content,
            "display_waiting_message": display_waiting_message
        }
        response: requests.Response = requests.post(url, json=payload, stream=True)
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                yield line.decode("utf-8")