# Import the task classes from other files
from common_tools.helpers.rag_service import RAGService

class RagInjectionPipeline:
    def __init__(self, rag: RAGService):
        self.rag_service: RAGService = rag

    def inject_documents(self, documents, doChunkContent = True):
        return self.rag_service.build_vectorstore_from(documents, doChunkContent)
        
       