
from langchain_community.llms import Ollama
from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv
from financial_crew import FinancialAnalystCrew

load_dotenv()

def run():
    inputs = {
        'company_name': 'Tesla',
    }
    #llm = Ollama(model="nous-hermes2")
    groq_api_key = os.getenv("GROQ_API_KEY")
    llm = ChatGroq(temperature=0, groq_api_key=groq_api_key, model_name="llama3-70b-8192")
    FinancialAnalystCrew(llm).crew().kickoff(inputs=inputs)

if __name__ == "__main__":
    run()   