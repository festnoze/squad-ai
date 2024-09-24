from pydantic import BaseModel, Field


class QuestionAnalysis:
    def __init__(self, question=None, translated_question=None, question_type=None, detected_language=None, **kwargs):
        # If a dictionary is provided, unpack its values
        if kwargs:
            self.question = kwargs.get('question', question)
            self.translated_question = kwargs.get('translated_question', translated_question)
            self.question_type = kwargs.get('question_type', question_type).lower()
            self.detected_language = kwargs.get('detected_language', detected_language).lower()
        else:
            # Assign individual arguments
            self.question = question
            self.translated_question = translated_question
            self.question_type = question_type.lower()
            self.detected_language = detected_language.lower()
     
class QuestionAnalysisPydantic(BaseModel):
    question: str = Field(description="The question to analyze")
    translated_question: str = Field(description="The translated question")
    question_type: str = Field(description="The type of the question")
    detected_language: str = Field(description="The language of the question")