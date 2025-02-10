import requests

class APIClient:
    def __init__(self, base_url: str) -> None:
        self.base_url: str = base_url

    def generate_all_summaries(self, files_batch_size: int, llm_batch_size: int, code_folder_path: str) -> dict:
        payload: dict = {
            "files_batch_size": files_batch_size,
            "llm_batch_size": llm_batch_size,
            "code_folder_path": code_folder_path
        }
        response = requests.post(f"{self.base_url}/generate_all_summaries", json=payload)
        return response.json()

    def analyse_files_code_structures(self, files_batch_size: int, code_folder_path: str) -> dict:
        payload: dict = {
            "files_batch_size": files_batch_size,
            "code_folder_path": code_folder_path
        }
        response = requests.post(f"{self.base_url}/analyse_files", json=payload)
        return response.json()

    def rebuild_vectorstore(self) -> dict:
        response = requests.post(f"{self.base_url}/rebuild_vectorstore")
        return response.json()

    def rag_query(self, query: str, include_bm25_retrieval: bool = False) -> dict:
        payload: dict = {"query": query, "include_bm25_retrieval": include_bm25_retrieval}
        headers = {"Content-Type": "application/json"}
        response = requests.post(f"{self.base_url}/rag/query", json=payload)
        return response.json()
    
    def rag_query_stream(self, query: str, include_bm25_retrieval: bool = False):
        body: dict = {"query": query, "include_bm25_retrieval": include_bm25_retrieval}
        headers = {"Content-Type": "application/json"}
        url = f"{self.base_url}/rag/query/stream"

        with requests.post(url, json=body, headers=headers, stream=True) as resp:
            if not resp.ok:
                raise requests.exceptions.HTTPError(
                    f"Answer user query request failed with status code {resp.status_code}, payload: {resp.text}"
                )

            try:
                for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
                    if chunk.strip():  # Only yield non-empty chunks
                        yield chunk
            except Exception as e:
                raise RuntimeError("Error processing streaming response.") from e
