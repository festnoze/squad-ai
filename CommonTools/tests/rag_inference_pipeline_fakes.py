class RAGGuardrailsFake:
    @staticmethod
    def guardrails_query_analysis(query):
        return "Guardrails Result", {"query": query}

class RAGPreTreatmentFake:
    @staticmethod
    def analyse_query_language(query):
        return "Language Analysis", {"query": query}

    @staticmethod
    def analyse_query_for_metadata(query):
        return "Metadata Analysis", {"query": query}

    @staticmethod
    def extract_explicit_metadata(query):
        return "Explicit Metadata", {"query": query}

class RAGHybridRetrievalFake:
    @staticmethod
    def map_previous_results():
        return "Mapped Results", {"results": []}

    @staticmethod
    def rag_retrieval():
        return "RAG Retrieval Result", {"retrieved_data": []}

    @staticmethod
    def bm25_retrieval():
        return "BM25 Retrieval Result", {"retrieved_data": []}

class RAGAugmentedGenerationFake:
    @staticmethod
    def answer_generation():
        return "Generated Answer", {"answer": "Answer"}

class RAGPostTreatmentFake:
    @staticmethod
    def response_post_treatment():
        return "Post-Treatment Result", {"post_processed": True}
