
import os
import datetime
import uuid
from langsmith import Client

def initialize_langsmith():
    langsmith_api_key = os.getenv("LANGCHAIN_API_KEY")

    # Setup and activate LangSmith 
    os.environ["LANGCHAIN_API_KEY"] = langsmith_api_key
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
    client = Client(api_key=langsmith_api_key)

    # langsmith_project = str(os.getenv("LANGCHAIN_PROJECT")) # Use the generic LangSmith project
    langsmith_project = str(os.getenv("LANGCHAIN_PROJECT") + str(uuid.uuid4())) # Add a specific LangSmith projetc for this session
    session = client.create_project(
        project_name=langsmith_project,
        description=f"Session of project '{os.getenv('LANGCHAIN_PROJECT')}' began on: {datetime.datetime.now().strftime('%d/%m/%Y at: %H:%M:%S')}",
    )
    os.environ["LANGCHAIN_PROJECT"] = langsmith_project

    # Add a database to LangSmith
    dl_dataset = client.create_dataset(
    dataset_name="dataset_" + langsmith_project,
    description="A set containing tests samples for the project",
    data_type="kv",  # ls_schemas.DataType.kv/chat/llm
    )
    client.create_example(
        inputs={"input": "test1"},
        outputs={"output": "res1"},
        dataset_id=dl_dataset.id,
    )