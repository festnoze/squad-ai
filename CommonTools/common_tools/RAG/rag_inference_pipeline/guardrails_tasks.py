import time

from common_tools.helpers.txt_helper import txt

class RAGGuardrails:
    @staticmethod
    def guardrails_query_analysis(query) -> bool:
        time.sleep(0.5) #todo: to implement
        if "bad query" in query:
            return False
        txt.print(">>> Query accepted by guardrails")
        return True
