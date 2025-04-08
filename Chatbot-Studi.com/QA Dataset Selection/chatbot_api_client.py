import requests

class ChatbotApiClient:
    def __init__(self, host_uri: str) -> None:
        self.host_uri = host_uri
        self.evaluation_prefix = f"{self.host_uri}/rag/evaluation"

    ### Evaluation endpoints ###
    def create_QA_dataset(self, samples_count_by_metadata: int = 10, limited_to_specified_metadata = None, output_file: str = None) -> requests.Response:
        params: dict[str, any] = {"samples_count_by_metadata": samples_count_by_metadata}
        if output_file is not None: params["output_file"] = output_file
        if limited_to_specified_metadata is not None: params["limited_to_specified_metadata"] = limited_to_specified_metadata
        return requests.post(f"{self.evaluation_prefix}/create-QA-dataset", params=params)
        
    def run_inference(self, dataset: dict, output_file: str = None) -> requests.Response:
        params: dict[str, any] = {"dataset": dataset}
        if output_file is not None: params["output_file"] = output_file
        return requests.post(f"{self.evaluation_prefix}/run-inference", params=params)

    def evaluate(self, dataset: dict) -> requests.Response:
        params: dict[str, any] = {"testset": dataset}
        return requests.post(f"{self.evaluation_prefix}/evaluate", params=params)