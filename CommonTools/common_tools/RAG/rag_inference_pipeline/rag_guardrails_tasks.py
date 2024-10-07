import time
from common_tools.helpers.txt_helper import txt
from common_tools.workflows.output_name_decorator import output_name

class RAGGuardrails:
    @staticmethod
    @output_name('guardrails_result')
    def guardrails_query_analysis(query) -> bool:
        time.sleep(0.5) #todo: to implement
        if "bad query" in query:
            return False
        #txt.print(">>> Query accepted by guardrails")
        return True
