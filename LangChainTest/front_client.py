import httpx
from streaming import stream

class front_client:
    host_uri = "http://localhost:5132"
    frontend_proxy_subpath = "FrontendProxy"
    message_content_stream_url_post = "metier-po/message-content-stream"

    async def send_stream_to_api_async(question):
        url = f"{front_client.host_uri}/{front_client.frontend_proxy_subpath}/{front_client.message_content_stream_url_post}" 
        async with httpx.AsyncClient() as http_client:
            # Prepare the stream as an asynchronous generator
            content_stream = stream.get_chatgpt_answer_as_stream_async(question)
            headers = {"Content-Type": "application/octet-stream"}
            # Stream the data to the API endpoint
            response = await http_client.post(url, content=content_stream, headers=headers)
            if (response.status_code == 200):
                print(" [stream sent]")