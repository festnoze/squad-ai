from typing import AsyncGenerator
import httpx
import requests 
from requests.exceptions import HTTPError
import json
# internal import
from misc import misc
from models.conversation import Message

class front_client:
    host_uri = "http://localhost:5132"
    frontend_proxy_subpath = "FrontendProxy"

    metier_brief_url_get = "metier/brief"
    validated_metier_answer_url_get = "metier/last-answer"
    new_metier_pm_message_url_post = "metier-po/new-message"
    update_last_metier_pm_message_url_post = "metier-po/update-last-message"
    delete_metier_pm_thread_url_delete = "metier-po/delete-all"
    new_po_us_and_usecases_url_post = "po/us"
    ping_url_get = "ping"

    def ping_front_until_responding():        
        sleep_interval = 2
        while front_client.does_ping_front_succeed() == False:
            misc.pause(sleep_interval)

    def does_ping_front_succeed():
        url = f"{front_client.host_uri}/{front_client.frontend_proxy_subpath}/{front_client.ping_url_get}"
        try:
            response = requests.get(url)
            return front_client.does_request_succeed(response) and response.text == "pong"
        except Exception:
            return False
    
    def get_metier_brief_if_ready():        
        url = f"{front_client.host_uri}/{front_client.frontend_proxy_subpath}/{front_client.metier_brief_url_get}"
        response = requests.get(url)
        if front_client.does_request_succeed(response):
            return response.text
        return ""

    def wait_need_expression_creation_and_get():
        sleep_interval = 1
        brief_str = front_client.get_metier_brief_if_ready()
        while brief_str == "":
            misc.pause(sleep_interval)
            brief_str = front_client.get_metier_brief_if_ready()
        return brief_str
    
    def get_validated_metier_answer_if_ready():        
        url = f"{front_client.host_uri}/{front_client.frontend_proxy_subpath}/{front_client.validated_metier_answer_url_get}"
        response = requests.get(url)
        if front_client.does_request_succeed(response):
            return response.text
        return ""

    def wait_metier_answer_validation_and_get():
        sleep_interval = 2
        metier_answer_str = front_client.get_validated_metier_answer_if_ready()
        while metier_answer_str == "":
            misc.pause(sleep_interval)
            metier_answer_str = front_client.get_validated_metier_answer_if_ready()
        return metier_answer_str
    
    def post_new_metier_or_pm_answer(message: Message):
        message_json = misc.get_message_as_json(message)
        url = f"{front_client.host_uri}/{front_client.frontend_proxy_subpath}/{front_client.new_metier_pm_message_url_post}"        
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, data= json.dumps(message_json), headers= headers)
        front_client.print_response_status(response, front_client.post_new_metier_or_pm_answer.__name__)

    def post_update_last_metier_or_pm_answer(message: Message):
        message_json = misc.get_message_as_json(message)
        url = f"{front_client.host_uri}/{front_client.frontend_proxy_subpath}/{front_client.update_last_metier_pm_message_url_post}"        
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, data= json.dumps(message_json), headers= headers)
        front_client.print_response_status(response, front_client.post_new_metier_or_pm_answer.__name__)

    async def post_new_metier_or_pm_answer_as_stream(content_stream: AsyncGenerator[bytes, None]):
        url = f"{front_client.host_uri}/{front_client.frontend_proxy_subpath}/{front_client.new_metier_pm_message_url_post}/stream"  
        async with httpx.AsyncClient() as http_client:            
            headers = {"Content-Type": "application/octet-stream"}
            # Stream the data to the API endpoint
            response = await http_client.post(url, content=content_stream, headers=headers)
            if (response.status_code == 200):
                print(" [end sent]")
        
    def delete_all_metier_po_thread(throw_upon_error = True):
        url = f"{front_client.host_uri}/{front_client.frontend_proxy_subpath}/{front_client.delete_metier_pm_thread_url_delete}"
        response = requests.delete(url)        
        return response

    def post_po_us_and_usecases(us_and_usecases_json):
        url = f"{front_client.host_uri}/{front_client.frontend_proxy_subpath}/{front_client.new_po_us_and_usecases_url_post}"        
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, data= json.dumps(us_and_usecases_json), headers= headers)
        front_client.print_response_status(response, front_client.post_po_us_and_usecases.__name__)
    
    def post_qa_acceptance_tests(us_and_usecases_json):
        url = f"{front_client.host_uri}/{front_client.frontend_proxy_subpath}/{front_client.new_po_us_and_usecases_url_post}"        
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, data= json.dumps(us_and_usecases_json), headers= headers)
        front_client.print_response_status(response, front_client.post_po_us_and_usecases.__name__)

    def print_response_status(response, method_name, throw_upon_error = True):
        if front_client.does_request_succeed(response) :
            print(f"Request '{method_name.replace("_", " ")}' successfully to the front.")
        else:
            print(f"Failed to request '{method_name.replace("_", " ")}' to the front. Status code: {response.status_code}, Response: {response.text}")
            if throw_upon_error:
                raise HTTPError(response= response)
            
    def does_request_succeed(response):
        return response.status_code >= 200 and response.status_code < 300
