import time
from typing import Optional, Union
from common_tools.helpers.txt_helper import txt
from common_tools.models.conversation import Conversation
from common_tools.workflows.output_name_decorator import output_name

class RAGGuardrails:
    @staticmethod
    @output_name('guardrails_result')
    def guardrails_query_analysis(query:Optional[Union[str, Conversation]]) -> bool:
        #time.sleep(0.5) #todo: to implement
        user_query = Conversation.get_user_query(query)
        if user_query == "bad query":
            return False
        return True
