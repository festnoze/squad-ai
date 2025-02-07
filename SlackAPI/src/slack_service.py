import os
import re
import requests
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv, find_dotenv

from helper import Helper

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
    
    def post_no_stream_response_to_query_from_external_api(self, channel, query):
        url = self.EXTERNAL_API_HOST 
        if self.EXTERNAL_API_PORT:
            url += ':' + self.EXTERNAL_API_PORT
        url += self.EXTERNAL_API_QUERY_ENDPOINT_URL
        
        body = {'query': query, 'type': 'slack', 'user_name': channel}
        response: requests.Response = requests.post(url, json=body)
        response.raise_for_status()
        answer = response.json()
    
        result = self.client.chat_postMessage(channel=channel, text= Helper.convert_markdown(answer), mrkdwn=True)
        return result['ts']
    
    new_line_for_stream_over_http = "\\/%*/\\" # use specific new line conversion over streaming, as new line is handled differently across platforms

    def post_streaming_response_to_query_from_external_api(self, channel, query, waiting_msg_id):
        url = self.EXTERNAL_API_HOST 
        if self.EXTERNAL_API_PORT:
            url += ':' + self.EXTERNAL_API_PORT
        url += self.EXTERNAL_API_STREAMING_QUERY_ENDPOINT_URL        
        body = {'query': query, 'type': 'slack', 'user_name': channel}
        
        response: requests.Response = requests.post(url, json=body, stream=True)
        response.raise_for_status()
        
        msg_response = self.client.chat_postMessage(channel=channel, text="...", mrkdwn=True)
        
        msg_ts: str = msg_response["ts"]
        full_response: str = ""
        
        for chunk in Helper.iter_words_then_lines(response, switch_to_line_chunk_after_words_count=15, decode_unicode=True):
            if chunk:
                if waiting_msg_id: 
                    self.delete_message(channel, waiting_msg_id)
                    waiting_msg_id = None
                full_response += chunk.replace(SlackService.new_line_for_stream_over_http, '\r\n')
                self.client.chat_update(channel=channel, ts=msg_ts, text=Helper.convert_markdown(full_response), mrkdwn=True)
        return msg_ts
            
    
    def delete_message(self, channel: str, timestamp: str) -> None:
        try:
            response = self.client.chat_delete(channel=channel, ts=timestamp)
            print("Message supprimé avec succès :", response)
        except SlackApiError as e:
            print(f"Erreur lors de la suppression du message : {e.response['error']}")

    def ping_external_api(self)-> str:
        url = self.EXTERNAL_API_HOST 
        if self.EXTERNAL_API_PORT:
            url += ':' + self.EXTERNAL_API_PORT
        url += "/ping"
        response: requests.Response = requests.get(url)
        response.raise_for_status()
        return response.text