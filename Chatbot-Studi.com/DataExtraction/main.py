from drupaljsonapi import DrupalJsonApiClient
from common_tools.helpers import txt, file, json
from common_tools.models import FileAlreadyExistsPolicy
from helpers.unicode_helper import UnicodeHelper

# Load environment variables from .env file
print("Starting...")

txt.activate_print = True
out_dir = "C:/Dev/squad-ai/Chatbot-Studi.com/DataExtraction/outputs/"
studiClient = DrupalJsonApiClient()

def save_json_file(filename, data):
    data_str = json.dumps(data, indent=4)
    data_str = UnicodeHelper.replace_ambiguous_unicode_characters(data_str)
    file.write_file(data_str, f"{out_dir}{filename}.json", FileAlreadyExistsPolicy.Override)

# Retrieve all jobs from studi.com
jobs = studiClient.get_jobs()
save_json_file("jobs", jobs)

# data = file.get_as_str(out_dir + "jobs.json", encoding='utf-8-sig')
# data = json.loads(data)
# txt.print_json(data[0])

# # Retrieve all fundings from studi.com
# fundings = studiClient.get_fundings()
# save_json_file("fundings", fundings)

# Retrieve all trainings from studi.com
trainings = studiClient.get_trainings()
save_json_file("trainings", trainings)
