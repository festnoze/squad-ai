from pydantic import BaseModel, Field
from common_tools.models.question_analysis_base import QuestionAnalysisBase, QuestionAnalysisBasePydantic

class DocChunk:
    def __init__(self, chunk_text: str = ''):
        self.text = chunk_text

class Question:
    def __init__(self, text: str = ''):
        self.text = text

class DocSummary:
    def __init__(self, doc_content: str = None, doc_summary: str = None, doc_chunks_to_questions: dict = None, **kwargs):
        if kwargs:
            self.doc_content = kwargs.get('doc_content', doc_content)
            self.doc_summary = kwargs.get('doc_summary', doc_summary)
            self.doc_chunks_to_questions = self.get_typed_chunks_with_their_questions(kwargs.get('doc_chunks_to_questions', doc_chunks_to_questions))
        else:
            self.doc_content = doc_content
            self.doc_summary = doc_summary
            self.doc_chunks_to_questions = self.get_typed_chunks_with_their_questions(doc_chunks_to_questions)
    
    def get_typed_chunks_with_their_questions(self, chunks_and_questions_dict: dict) -> list[tuple[DocChunk, list[Question]]]:
        chunks_with_questions_typed = []        
        for chunk_text, questions in chunks_and_questions_dict.items():
            doc_chunk = DocChunk(chunk_text)
            question_list = [Question(question_text) for question_text in questions]
            chunks_with_questions_typed.append((doc_chunk, question_list))        
        return chunks_with_questions_typed

# Pydantic models
class DocChunkPydantic(BaseModel):
    chunk_text: str = Field(description="Le texte d'une partie (chunk) du résumé du document.")

class QuestionPydantic(BaseModel):
    question_text: str = Field(description="Une question atomique et complète portant sur une partie du texte du document.")

class DocSummaryPydantic(BaseModel):
    doc_summary: str = Field(description="Résumé complet et structuré du contenu du document")
    doc_chunks_to_questions: dict[DocChunkPydantic, list[QuestionPydantic]] = Field(
        description="Dictionnaire où chaque clé contient un chunk du résumé du document, et chaque valeur contient la liste des questions unitaires correspondantes à ce chunk."
    )

