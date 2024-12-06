# /!\ 'load_dotenv()'  Must be done beforehand in the main script!
import os

class EnvHelper:
    @staticmethod
    def get_openai_api_key():
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set in the environment")
        return openai_api_key
    
    @staticmethod
    def get_anthropic_api_key():
        anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
        if not anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set in the environment")
        return anthropic_api_key
    
    @staticmethod
    def get_groq_api_key():
        groq_api_key = os.getenv('GROQ_API_KEY')
        if not groq_api_key:
            raise ValueError("GROQ_API_KEY is not set in the environment")
        return groq_api_key

    @staticmethod
    def get_pinecone_api_key():
        pinecone_api_key = os.getenv('PINECONE_API_KEY')
        if not pinecone_api_key:
            raise ValueError("PINECONE_API_KEY is not set in the environment")
        return pinecone_api_key
    
    @staticmethod
    def get_pinecone_environment():
        pinecone_environment = os.getenv('PINECONE_ENVIRONMENT')
        if not pinecone_environment:
            raise ValueError("PINECONE_ENVIRONMENT is not set in the environment")
        return pinecone_environment
    
    # Use VECTOR_DB_NAME from ConfigHelper instead
    # @staticmethod
    # def get_pinecone_index_name():
    #     pinecone_index_name = os.getenv('PINECONE_INDEX_NAME')
    #     if not pinecone_index_name:
    #         raise ValueError("PINECONE_INDEX_NAME is not set in the environment")
    #     return pinecone_index_name
    