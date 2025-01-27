from unittest.mock import patch, MagicMock
from langchain_chroma import Chroma
from langchain_core.documents import Document
from common_tools.rag.rag_inference_pipeline.rag_inference_pipeline import RagInferencePipeline
from common_tools.rag.rag_service import RagService
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.models.llm_info import LlmInfo
from common_tools.models.embedding_type import EmbeddingModel

class TestRagInferencePipelineIntegration:

    def setup_method(self):
        # Set up the necessary LLM information for the RAGService
        llms_infos = []
        #llms_infos.append(LlmInfo(type= LangChainAdapterType.Ollama, model= "phi3", timeout= 80, temperature = 0.5))
        llms_infos.append(LlmInfo(type= LangChainAdapterType.OpenAI, model= "gpt-3.5-turbo-0125",  timeout= 60, temperature = 0.5))
        #llms_infos.append(LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4o", timeout=80, temperature=0))
        
        docs: list[Document] = [
            Document(page_content="Choupicity is the capital of Choupiland.", metadata={"source": "Wikipedia"}),
            Document(page_content="The Eiffel Tower is a famous landmark in Paris.", metadata={"source": "Wikipedia"}),
            Document(page_content="The Louvre is a famous museum in Paris.", metadata={"source": "Wikipedia"}),
            Document(page_content="CCIAPF is the simulation of octopus intelligence in trees.", metadata={"source": "Wikipedia"}),
        ]

        with patch.object(RagService, '__init__', return_value=None):
            self.rag_service = RagService()
            self.rag_service.init_embedding(EmbeddingModel.OpenAI_TextEmbedding3Small)
            self.rag_service.init_inference_llm(llms_infos)
            self.rag_service.langchain_documents = docs
            self.rag_service.vectorstore = Chroma.from_documents(documents= docs, embedding = self.rag_service.embedding)
            #
            self.inference = RagInferencePipeline(self.rag_service)

    def test_inference_pipeline_run_dynamic_with_bm25_retrieval(self):
        # Define the query for the test
        query = "Quelle est la capitale de la Choupiland ?"
        
        response = self.inference.run_pipeline_dynamic(
            query, 
            include_bm25_retrieval=True, 
            give_score=True, 
            format_retrieved_docs_function=None
        )

        assert isinstance(response, str), "The response should be a string"
        # assert isinstance(sources, list), "The sources should be a list"
        # assert len(sources) > 0, "There should be at least one source retrieved"
        assert "Choupicity" in response, f"The response should mention the fake capital of Choupiland from the data: 'Choupicity', but was: '{response}'"

    def test_inference_pipeline_run_dynamic_without_bm25_retrieval(self):
        # Define the query for the test
        query = "Explain the concept of CCIAPF."

        # Run the inference pipeline without BM25 retrieval
        response = self.inference.run_pipeline_dynamic(
            query,
            include_bm25_retrieval=False, 
            give_score=True, 
            format_retrieved_docs_function=TestRagInferencePipelineIntegration.format_retrieved_docs_function
        )

        # Assertions to verify that the response and sources are valid
        assert isinstance(response, str), "The response should be a string"
        # assert isinstance(sources, list), "The sources should be a list"
        # assert len(sources) > 0, "There should be at least one source retrieved"
        #assert [ "I found! " source for source in sources], f"The response should mention 'I found! ' added by the formatting function, but was: '{response}'"
        assert response.lower().__contains__("octopus") or response.lower().__contains__("pieuvre") or response.lower().__contains__("poulpe"), f"The response should mention 'octopus', but was: '{response}'"

    def test_inference_pipeline_run_static_with_bm25_retrieval(self):
        # Define the query for the test
        query = "Quelle est la capitale de la Choupiland ?"
        
        response = self.inference.run_pipeline_static(
            query, 
            include_bm25_retrieval=True, 
            give_score=True, 
            format_retrieved_docs_function=None
        )

        assert isinstance(response, str), "The response should be a string"
        # assert isinstance(sources, list), "The sources should be a list"
        # assert len(sources) > 0, "There should be at least one source retrieved"
        assert "Choupicity" in response, f"The response should mention the fake capital of Choupiland from the data: 'Choupicity', but was: '{response}'"

    @staticmethod
    def format_retrieved_docs_function(retrieved_docs:list):
        if not any(retrieved_docs):
            return 'not a single information were found. Don\'t answer the question.'
        add_txt = "I found! "
        for doc in retrieved_docs:
            if isinstance(doc, tuple):
                doc[0].page_content = add_txt + doc[0].page_content
            elif isinstance(doc, Document):
                doc.page_content = add_txt + doc.page_content
            elif isinstance(doc, str):
                doc = add_txt + doc
            else:
                raise ValueError("Invalid document type")
        
        return retrieved_docs

    # def test_inference_pipeline_custom_format_function(self):
    #     # Define the query for the test
    #     query = "What is the importance of quantum computing?"

    #     # Define a custom formatting function
    #     def custom_format_function(docs):
    #         return f"Custom Format: {docs}"

    #     # Run the inference pipeline with a custom formatting function
    #     response, sources = self.inference.run_pipeline_dynamic(
    #         query, 
    #         include_bm25_retrieval=True, 
    #         give_score=False, 
    #         format_retrieved_docs_function=custom_format_function
    #     )

    #     # Assertions to verify that the response and sources are valid and custom formatted
    #     assert isinstance(response, str), "The response should be a string"
    #     assert isinstance(sources, list), "The sources should be a list"
    #     assert len(sources) > 0, "There should be at least one source retrieved"
    #     assert [ "I found! " source for source in sources], f"The response should mention 'I found! ' added by the formatting function, but was: '{response}'"
    #     assert "Custom Format" in response, "The response should contain the custom formatted output"

