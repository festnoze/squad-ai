
import os
import datetime
from typing import Iterator
import uuid
from langsmith import Client
from langsmith.schemas import Example, Run

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

    def create_project(self, specific_session = False):
        self.langsmith_project_session = self.langsmith_project_name 
        if specific_session:
            self.langsmith_project_session += '_' + str(uuid.uuid4().hex[0:6]) # Add a specific LangSmith project for this session
        else:
             self.delete_all_project_sessions()
        self.session = self.client.create_project(
            project_name= self.langsmith_project_session,
            description= f"{datetime.datetime.now().strftime('%d/%m/%Y at: %H:%M:%S')} session of: '{self.langsmith_project_name}'",
        )
        return self.session

    def create_dataset(self):
        self.dl_dataset = self.client.create_dataset(
            dataset_name="dataset_" + self.langsmith_project_session,
            description="A set containing tests samples for the project",
            data_type="kv", 
        )
        self.client.create_example(
            inputs={"input": "test1"},
            outputs={"output": "res1"},
            dataset_id=self.dl_dataset.id,
        )

    def get_dataset_examples(self, dataset_name: str) -> Iterator[Example]:
        return self.client.list_examples(dataset_id=dataset_name)

    def get_all_projects(self):
        return list(self.client.list_projects())

    # Main function to delete all projects
    def delete_all_project_sessions(self):
        projects = self.get_all_projects()
        for project in projects:
            if project.name.startswith(self.langsmith_project_name):
                self.client.delete_project(project_name=project.name)