import os
import re
import requests
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv, find_dotenv

from helper import Helper

class SlackService:
    SLACK_BOT_TOKEN: str = None
    SLACK_SIGNING_SECRET: str = None
    SLACK_BOT_USER_ID: str = None
    HTTP_SCHEMA: str = None
    EXTERNAL_API_HOST: str = None
    EXTERNAL_API_PORT: str = None
    EXTERNAL_API_QUERY_ENDPOINT_URL: str = None
    EXTERNAL_API_STREAMING_QUERY_ENDPOINT_URL: str = None
    STREAMING_RESPONSE: str = None     
    new_line_for_stream_over_http = "\\/%*/\\" # use specific new line conversion over streaming, as new line is handled differently across platforms

    def __init__(self):
        if SlackService.SLACK_BOT_TOKEN is None:   
            load_dotenv(find_dotenv())
            SlackService.SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
            SlackService.SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
            SlackService.SLACK_BOT_USER_ID = os.environ["SLACK_BOT_USER_ID"]
            SlackService.HTTP_SCHEMA = os.environ["HTTP_SCHEMA"]
            SlackService.EXTERNAL_API_HOST = os.environ["EXTERNAL_API_HOST"]
            SlackService.EXTERNAL_API_PORT = os.environ["EXTERNAL_API_PORT"]
            SlackService.EXTERNAL_API_QUERY_ENDPOINT_URL = os.environ["EXTERNAL_API_QUERY_ENDPOINT_URL"]
            SlackService.EXTERNAL_API_STREAMING_QUERY_ENDPOINT_URL = os.environ["EXTERNAL_API_STREAMING_QUERY_ENDPOINT_URL"]
            SlackService.STREAMING_RESPONSE = os.environ["STREAMING_RESPONSE"].lower() == 'true'

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

    # Handle both streaming and non streaming answer to user query provided by the external API    
    def post_response_to_query_from_external_api(self, channel, query, waiting_msg_to_delete_ts):
        if not SlackService.STREAMING_RESPONSE:
            return self.post_no_stream_response_to_query_from_external_api(channel, query, waiting_msg_to_delete_ts)
        else:
            return self.post_streaming_response_to_query_from_external_api(channel, query, waiting_msg_to_delete_ts)

    def post_no_stream_response_to_query_from_external_api(self, channel, query, waiting_msg_to_delete_ts):
        url = self.HTTP_SCHEMA + "://" + self.EXTERNAL_API_HOST 
        if self.EXTERNAL_API_PORT:
            url += ':' + self.EXTERNAL_API_PORT
        url += self.EXTERNAL_API_QUERY_ENDPOINT_URL
        
        body = {'query': query, 'type': 'slack', 'user_name': channel}
        response: requests.Response = requests.post(url, json=body)
        response.raise_for_status()
        answer = response.json()
    
        result = self.client.chat_postMessage(channel=channel, text= Helper.convert_markdown(answer), mrkdwn=True)
        
        if waiting_msg_to_delete_ts: 
            self.delete_message(channel, waiting_msg_to_delete_ts)
            waiting_msg_to_delete_ts = None
        return result['ts']
   
    def post_streaming_response_to_query_from_external_api(self, channel, query, waiting_msg_to_delete_ts):
        url = self.HTTP_SCHEMA + "://" + self.EXTERNAL_API_HOST 
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
                if waiting_msg_to_delete_ts: 
                    self.delete_message(channel, waiting_msg_to_delete_ts)
                    waiting_msg_to_delete_ts = None
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
        url = self.HTTP_SCHEMA + "://" + self.EXTERNAL_API_HOST 
        if self.EXTERNAL_API_PORT:
            url += ':' + self.EXTERNAL_API_PORT
        url += "/ping"
        response: requests.Response = requests.get(url)
        response.raise_for_status()
        return response.text