class RAGPostTreatment:
    @staticmethod
    def rag_post_treatment(response):
        return RAGPostTreatment.response_post_treatment(response)
    
    @staticmethod
    def response_post_treatment(response):
        return response
