from dotenv import load_dotenv
from langchain_community.llms import Ollama

load_dotenv()

from config.financial_crew import FinancialAnalystCrew

def run():
    inputs = {
        'company_name': 'Tesla',
    }
    ollama_llm = Ollama(model="nous-hermes2")
    FinancialAnalystCrew(ollama_llm).crew().kickoff(inputs=inputs)

if __name__ == "__main__":
    run()   