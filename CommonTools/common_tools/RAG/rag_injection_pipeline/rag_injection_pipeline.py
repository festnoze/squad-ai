from common_tools.RAG.rag_service import RAGService

class RagInjectionPipeline:
    def __init__(self, rag: RAGService):
        self.rag_service: RAGService = rag

    def inject_documents(self, documents, perform_chunking = True, delete_existing=True):
        return self.rag_service.build_vectorstore_and_bm25_store(documents, perform_chunking, delete_existing)
        
       