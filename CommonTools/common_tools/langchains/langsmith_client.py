
import os
import datetime
import uuid
from langsmith import Client
import requests

from common_tools.helpers.txt_helper import txt

class Langsmith:
    def __init__(self):
        self.langsmith_api_key = os.getenv("LANGCHAIN_API_KEY")
        self.langsmith_project_name = str(os.getenv("LANGCHAIN_PROJECT"))
        self.langsmith_host_uri = "https://api.smith.langchain.com"
        self.headers = {
            'Authorization': f'Bearer {self.langsmith_api_key}',
            'Content-Type': 'application/json'
        }
        os.environ["LANGCHAIN_API_KEY"] = self.langsmith_api_key
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = self.langsmith_host_uri
        self.client = Client(api_key=self.langsmith_api_key)

    def create_project(self):
        self.langsmith_project_session = self.langsmith_project_name + '_' + str(uuid.uuid4().hex[0:6]) # Add a specific LangSmith project for this session
        self.session = self.client.create_project(
            project_name= self.langsmith_project_session,
            description= f"{datetime.datetime.now().strftime('%d/%m/%Y at: %H:%M:%S')} session of: '{self.langsmith_project_name}'",
        )
        txt.print(f"Langsmith project '{self.langsmith_project_session}' created")
        return self.session

    def create_dataset(self):
        self.dl_dataset = self.client.create_dataset(
            dataset_name="dataset_" + self.langsmith_project_session,
            description="A set containing tests samples for the project",
            data_type="kv",  # ls_schemas.DataType.kv/chat/llm
        )
        self.client.create_example(
            inputs={"input": "test1"},
            outputs={"output": "res1"},
            dataset_id=self.dl_dataset.id,
        )

    def get_all_projects(self):
        return list(self.client.list_projects())

    # Main function to delete all projects
    def delete_all_project_sessions(self):
        projects = self.get_all_projects()
        for project in projects:
            if project.name.startswith(self.langsmith_project_name): # and project.name != self.langsmith_project_name:
                self.client.delete_project(project_name=project.name)
                print(f"Langsmith project '{project.name}' deleted")
        print("Langsmith All related projects deleted.")