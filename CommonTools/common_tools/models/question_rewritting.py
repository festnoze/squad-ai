from pydantic import BaseModel, Field
from common_tools.models.question_analysis_base import QuestionAnalysisBase, QuestionAnalysisBasePydantic

class QuestionRewritting(QuestionAnalysisBase):
    def __init__(self, question, has_contextual_info=False, question_with_context=None, modified_question=None, question_type=None, **kwargs):
        # If a dictionary is provided, unpack its values
        if kwargs:
            super().__init__(kwargs.get('question', question), kwargs.get('completed_question', modified_question))
            self.has_contextual_info = kwargs.get('has_contextual_info', has_contextual_info)
            self.question_with_context = kwargs.get('question_with_context', question_with_context)
            self.question_type = kwargs.get('question_type', question_type).lower()
        else:
            # Assign individual arguments
            super().__init__(question, modified_question if modified_question else question)
            self.has_contextual_info = has_contextual_info
            self.question_with_context = question_with_context if question_with_context else question
            self.question_type = question_type.lower() if question_type else 'other'

     
class QuestionRewrittingPydantic(QuestionAnalysisBasePydantic):
    has_contextual_info: bool = Field(description="Whether the conversation's history has needed contextual information to complete the user''s query")
    question_with_context: str = Field(description="The user''s query completed with the context information from the conversation history")
    question_type: str = Field(description="The type of the question as a string. One value in: ['salutations', 'fin_echange', 'autre']")#. One value in: ['greetings', 'ending', 'studi', 'job', 'training', 'funding', 'other'].")