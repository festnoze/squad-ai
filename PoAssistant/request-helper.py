import requests 
from requests.exceptions import HTTPError
def post_moe_answer(url):
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data
    
    raise HTTPError(response= response)