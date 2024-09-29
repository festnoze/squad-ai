# Import the task classes from other files
from common_tools.helpers.rag_service import RAGService

class RagInjectionPipeline:
    def __init__(self, rag: RAGService):
        self.rag: RAGService = rag

    def inject_documents(self, documents):
        for doc in documents:
            self.rag.inject_document(doc)
    
    def inject_document(self, document):
        self.rag.inject_document(document)
       