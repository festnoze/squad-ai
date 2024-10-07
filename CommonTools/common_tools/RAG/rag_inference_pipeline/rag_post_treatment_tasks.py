from common_tools.models.question_analysis import QuestionAnalysis

class RAGPostTreatment:
    @staticmethod
    def rag_post_treatment(guardrails_result: bool, rag_answer: str, analysed_query: QuestionAnalysis):
        return RAGPostTreatment.response_post_treatment(guardrails_result, rag_answer, analysed_query)
    
    @staticmethod
    def response_post_treatment(guardrails_result: bool, rag_answer: list[str], analysed_query: QuestionAnalysis):
        if guardrails_result == True:
            return rag_answer[0]
        else:
            if analysed_query.detected_language == "french":
                return "Je ne peux pas répondre à votre question, car son sujet est explicitement interdit."
            else:
                return "I cannot answer your question, because its topic is explicitly forbidden."
