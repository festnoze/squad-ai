import requests
import gitlab

# Set your access token, project ID, and merge request ID
ACCESS_TOKEN = '_2ZMBnRSXK4miatXKuyi'
PROJECT_ID = '350' # studi.api.core
MERGE_REQUEST_ID = '82'
GITLAB_URL = 'https://gitdev.studi.fr'
url = f"{GITLAB_URL}/api/v4/projects/{PROJECT_ID}/merge_requests/{MERGE_REQUEST_ID}/changes"
# Headers for authentication
headers = {
    'Authorization': f'{ACCESS_TOKEN}',
    'Content-Type': 'application/json'
}

# Optionally, add parameters to filter the results
params = {
    'state': 'opened',  # Example to list only open merge requests
    'order_by': 'updated_at',  # Order by last updated merge requests
    'sort': 'desc'  # Sort in descending order
}

# Make the API request
response = requests.get(url, headers=headers, params=params)
# Make the API request
response = requests.get(url, headers=headers)

# Check the response status
if response.status_code == 200:
    changes = response.json()
    print("Changes in Merge Request:")
    print(changes)
else:
    print("Failed to fetch merge request changes:", response.status_code, response.text)

