import requests 
from requests.exceptions import HTTPError
import json
from misc import misc

class front_client:
    host_uri = "http://localhost:5132"
    frontend_proxy_subpath = "FrontendProxy"

    new_metier_po_message_url_post = "metier-po/new-message"
    new_metier_po_message_url_post = "metier-po/new-message"
    delete_metier_po_thread_url_delete = "metier-po/delete-all"
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

    def post_new_metier_or_po_answer(message_json):
        url = f"{front_client.host_uri}/{front_client.frontend_proxy_subpath}/{front_client.new_metier_po_message_url_post}"        
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, data= json.dumps(message_json), headers= headers)
        front_client.print_response_status(response, front_client.post_new_metier_or_po_answer.__name__)
        
    def delete_all_metier_po_thread(throw_upon_error = True):
        url = f"{front_client.host_uri}/{front_client.frontend_proxy_subpath}/{front_client.delete_metier_po_thread_url_delete}"
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
