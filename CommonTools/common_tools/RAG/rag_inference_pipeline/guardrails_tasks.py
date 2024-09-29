import time

class RAGGuardrails:
    @staticmethod
    def guardrails_query_analysis(query) -> bool:
        time.sleep(3) #todo: to implement
        if "bad query" in query:
            return False
        print(">>> Query accepted by guardrails")
        return True
