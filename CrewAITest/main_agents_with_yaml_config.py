
from langchain_community.llms import Ollama
from dotenv import load_dotenv
load_dotenv()

from test_crew_yaml_config_files.financial_crew import FinancialAnalystCrew

def run():
    inputs = {
        'company_name': 'Tesla',
    }
    ollama_llm = Ollama(model="nous-hermes2")
    FinancialAnalystCrew(ollama_llm).crew().kickoff(inputs=inputs)

if __name__ == "__main__":
    run()   