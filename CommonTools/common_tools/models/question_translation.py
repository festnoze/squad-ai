from pydantic import BaseModel, Field

from common_tools.models.question_analysis_base import QuestionAnalysisBase, QuestionAnalysisBasePydantic

class QuestionTranslation(QuestionAnalysisBase):
    def __init__(self, question=None, translated_question=None, question_type=None, detected_language=None, **kwargs):
        # If a dictionary is provided, unpack its values
        if kwargs:
            super().__init__(kwargs.get('question', question), kwargs.get('translated_question', translated_question))
            self.question_type = kwargs.get('question_type', question_type).lower()
            self.detected_language = kwargs.get('detected_language', detected_language).lower()
        else:
            # Assign individual arguments
            super().__init__(question, translated_question)
            self.question_type = question_type.lower()
            self.detected_language = detected_language.lower()
     
class QuestionTranslationPydantic(QuestionAnalysisBasePydantic):
    detected_language: str = Field(description="The language of the question")