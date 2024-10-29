from pydantic import BaseModel, Field

class QuestionAnalysisBase:
    def __init__(self, question, modified_question=None, **kwargs):
        if kwargs:
            self.question = kwargs.get('question', question)
            self.modified_question = kwargs.get('modified_question', modified_question)
        else:
            self.question = question
            self.modified_question = modified_question

        if not self.modified_question:
            self.modified_question = self.question

    # handle dict rather than only object instance
    @staticmethod
    def get_modified_question(analysed_query):
        if hasattr(analysed_query, 'modified_question'):
            return analysed_query.modified_question
        elif isinstance(analysed_query, dict) and 'modified_question' in analysed_query:
            return analysed_query['modified_question']
        else:
            return analysed_query.question


    @staticmethod
    def set_modified_question(analysed_query, value):
        if hasattr(analysed_query, 'modified_question'):
            analysed_query.modified_question = value
        elif isinstance(analysed_query, dict) and 'modified_question' in analysed_query:
            analysed_query['modified_question'] = value    
     
class QuestionAnalysisBasePydantic(BaseModel):
    question: str = Field(description="The question to analyze")
    modified_question: str = Field(description="The question after being modified by analysis processes")