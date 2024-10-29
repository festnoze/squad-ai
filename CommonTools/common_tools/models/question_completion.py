from pydantic import BaseModel, Field
from common_tools.models.question_analysis_base import QuestionAnalysisBase, QuestionAnalysisBasePydantic

class QuestionCompletion(QuestionAnalysisBase):
    def __init__(self, question, has_contextual_info=False, completed_question=None, question_type=None, **kwargs):
        # If a dictionary is provided, unpack its values
        if kwargs:
            super().__init__(kwargs.get('question', question), kwargs.get('completed_question', completed_question))
            self.has_contextual_info = kwargs.get('has_contextual_info', has_contextual_info)
            self.question_type = kwargs.get('question_type', question_type).lower()
        else:
            # Assign individual arguments
            super().__init__(question, completed_question if completed_question else question)
            self.has_contextual_info = has_contextual_info
            self.question_type = question_type.lower() if question_type else 'other'

     
class QuestionCompletionPydantic(QuestionAnalysisBasePydantic):
    has_contextual_info: bool = Field(description="Whether the conversation's history has needed contextual information to complete the question")
    question_type: str = Field(description="The type of the question. One value in: ['greetings', 'ending', 'studi', 'job', 'training', 'funding', 'other'].")