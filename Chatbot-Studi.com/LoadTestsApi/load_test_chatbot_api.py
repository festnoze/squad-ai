from locust import HttpUser, task, between


################################
# - Load Testing - Chatbot API -
# To run the test, type to terminal:
#
# locust -f load_test_chatbot_api.py
#####################################

class RAGQueryUser(HttpUser):
    # Define the base URL for the host
    host = "http://127.0.0.1:8000"  # Localhost FastAPI app

    # Define the wait time between tasks
    wait_time = between(10, 20)

    @task
    def test_rag_query_stream(self):
        # Define the JSON payload for the POST request
        payload = {
            "messages": [
                {"role": "user", "content": "What is the capital of France?"},
                {"role": "system", "content": "The capital of France is Paris."}
            ]
        }

        # Send the POST request to the streaming endpoint
        with self.client.post(
            "/rag/query/stream",
            json=payload,
            stream=True,
            headers={"Content-Type": "application/json"},
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    for line in response.iter_lines():
                        print(line.decode("utf-8"))  # Process streamed lines
                except Exception as e:
                    response.failure(f"Failed to process streaming response: {str(e)}")
            else:
                response.failure(f"Unexpected status code: {response.status_code}")
