import os
import re
import requests
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv, find_dotenv

class SlackService:
    def __init__(self):       
        load_dotenv(find_dotenv())
        self.SLACK_BOT_TOKEN: str = os.environ["SLACK_BOT_TOKEN"]
        self.SLACK_SIGNING_SECRET: str = os.environ["SLACK_SIGNING_SECRET"]
        self.SLACK_BOT_USER_ID: str = os.environ["SLACK_BOT_USER_ID"]
        self.EXTERNAL_API_HOST: str = os.environ["EXTERNAL_API_HOST"]
        self.EXTERNAL_API_PORT: str = os.environ["EXTERNAL_API_PORT"]
        self.EXTERNAL_API_QUERY_ENDPOINT_URL: str = os.environ["EXTERNAL_API_QUERY_ENDPOINT_URL"]
        self.EXTERNAL_API_STREAMING_QUERY_ENDPOINT_URL: str = os.environ["EXTERNAL_API_STREAMING_QUERY_ENDPOINT_URL"]

        self.signature_verifier: SignatureVerifier = SignatureVerifier(self.SLACK_SIGNING_SECRET)
        self.client: WebClient = WebClient(token=self.SLACK_BOT_TOKEN)
        
    def is_valid_request(self, body_str, request):
        return self.signature_verifier.is_valid_request(body_str, request.headers)
    
    def get_user_id(self):
        user_id = self.SLACK_BOT_USER_ID
        if not user_id:
            response: dict = self.client.auth_test()
            user_id =  response["user_id"]
        return user_id
    
    def post_message(self, channel, message, mrkdwn=False):
        result = self.client.chat_postMessage(channel= channel, text= message, mrkdwn= mrkdwn)
        return result['ts']
    
    def post_response_to_query_from_external_api(self, channel, query):
        url = self.EXTERNAL_API_HOST 
        if self.EXTERNAL_API_PORT:
            url += ':' + self.EXTERNAL_API_PORT
        url += self.EXTERNAL_API_QUERY_ENDPOINT_URL
        
        body = {'query': query, 'type': 'slack', 'user_name': channel}
        response: requests.Response = requests.post(url, json=body)
        response.raise_for_status()
        answer = response.json()
    
        result = self.client.chat_postMessage(channel=channel, text= SlackService.convert_markdown(answer), mrkdwn=True)
        return result['ts']
    
    @staticmethod
    def convert_markdown(text):
        # Remplacer les doubles astérisques par des simples
        text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
        # Remplacer les doubles underscores par des simples
        text = re.sub(r'__(.*?)__', r'_\1_', text)
        return text
    
    def get_message_as_markdown_blocks(self, markdown_text):
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": markdown_text
                }
            }
        ]
        return blocks
    
    def delete_message(self, channel: str, timestamp: str) -> None:
        try:
            response = self.client.chat_delete(channel=channel, ts=timestamp)
            print("Message supprimé avec succès :", response)
        except SlackApiError as e:
            print(f"Erreur lors de la suppression du message : {e.response['error']}")