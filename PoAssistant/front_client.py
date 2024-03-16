import requests 
from requests.exceptions import HTTPError
import json

class front_client:
    host_uri = "http://localhost:5132"
    post_new_message_url = "FrontendProxy/moa-moe/new-message"

    def post_new_answer(message_json):
        url = f"{front_client.host_uri}/{front_client.post_new_message_url}"        
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, data= json.dumps(message_json), headers= headers)

        if response.status_code >= 200 and response.status_code < 300 :
            print("Message successfully sent to front.")
        else:
            print(f"Failed to send message to front. Status code: {response.status_code}, Response: {response.text}")
            raise HTTPError(response= response)
