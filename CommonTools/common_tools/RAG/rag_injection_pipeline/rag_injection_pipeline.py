from common_tools.rag.rag_service import RagService

class RagInjectionPipeline:
    def __init__(self, rag: RagService):
        self.rag_service: RagService = rag

    def inject_documents(self, documents, perform_chunking = True, delete_existing=True):
        return self.rag_service.build_vectorstore_and_bm25_store(documents, perform_chunking, delete_existing)
        
       