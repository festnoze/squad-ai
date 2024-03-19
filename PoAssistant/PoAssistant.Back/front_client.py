import requests 
from requests.exceptions import HTTPError
import json

class front_client:
    host_uri = "http://localhost:5132"
    frontend_proxy_subpath = "FrontendProxy"

    new_moe_moa_message_url_post = "metier-po/new-message"
    delete_moe_moa_thread_url_delete = "metier-po/delete"
    new_po_us_and_usecases_url_post = "po/us"

    def post_new_answer_moe_moa(message_json):
        url = f"{front_client.host_uri}/{front_client.frontend_proxy_subpath}/{front_client.new_moe_moa_message_url_post}"        
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, data= json.dumps(message_json), headers= headers)
        front_client.print_response_status(response, front_client.post_new_answer_moe_moa.__name__)
        
    def delete_new_moe_moa_thread():
        url = f"{front_client.host_uri}/{front_client.frontend_proxy_subpath}/{front_client.delete_moe_moa_thread_url_delete}"        
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.delete(url)
            front_client.print_response_status(response, front_client.delete_new_moe_moa_thread.__name__)
        except Exception as e:
            pass

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

    def print_response_status(response, method_name):
        if response.status_code >= 200 and response.status_code < 300 :
            print(f"Request '{method_name.replace("_", " ")}' successfully to the front.")
        else:
            print(f"Failed to request '{method_name.replace("_", " ")}' to the front. Status code: {response.status_code}, Response: {response.text}")
            raise HTTPError(response= response)
