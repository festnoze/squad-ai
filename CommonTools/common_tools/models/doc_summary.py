from pydantic import BaseModel, Field
import pandas as pd
#
from common_tools.helpers.txt_helper import txt
from common_tools.models.question_analysis_base import QuestionAnalysisBase, QuestionAnalysisBasePydantic


class Question:
    def __init__(self, text: str = ''):
        self.text = text

    def __repr__(self) -> str:
        return f"Question: {self.text})"

class DocChunk:
    def __init__(self, chunk_text: str = '', questions:list[Question] = []):
        self.text = chunk_text
        self.questions = questions
    
    def __repr__(self) -> str:
        return f"DocChunk: {self.chunk_text})"
class DocSummary:
    def __init__(self, doc_content: str = None, doc_summary: str = None, doc_chunks_with_questions: dict = None, **kwargs):
        if kwargs:
            self.doc_content:str = kwargs.get('doc_content', doc_content)
            self.doc_summary:str = kwargs.get('doc_summary', doc_summary)
            self.doc_chunks:list[DocChunk] = self.get_typed_chunks_with_their_questions(kwargs.get('doc_chunks', doc_chunks_with_questions))
        else:
            self.doc_content:str = doc_content
            self.doc_summary:str = doc_summary
            self.doc_chunks:list[DocChunk] = self.get_typed_chunks_with_their_questions(doc_chunks_with_questions)
    
    def get_typed_chunks_with_their_questions(self, chunks_and_questions_dict: dict) -> list[DocChunk]:
        chunks_with_questions_typed = []       
        for chunk_with_questions in chunks_and_questions_dict:
            questions = chunk_with_questions['questions']
            question_list = []
            if isinstance(questions[0], Question):
                question_list = questions
            else:
                for question in questions:
                    question_list.append(Question(question))
                
            doc_chunk = DocChunk(chunk_with_questions['chunk_text'], question_list)
            chunks_with_questions_typed.append(doc_chunk)      
        return chunks_with_questions_typed
    
    def display_to_terminal(self):
        data = []
        max_questions = 0
        data.append({'Summary: ': self.doc_summary})
        for i, chunk in enumerate(self.doc_chunks, start=1):
            row = [chunk.text] + [q.text for q in chunk.questions]
            data.append(row)
            max_questions = max(max_questions, len(chunk.questions))
        columns = ["Chunk Text"] + [f"Question n°{i+1}" for i in range(max_questions)]
        df = pd.DataFrame(data, columns=columns)
        df = df.fillna('')
        print(df.to_string(index=False))

# Pydantic models
class QuestionPydantic(BaseModel):
    question_text: str = Field(description="Une question atomique et complète portant sur une partie du chunk du document.")

class DocChunkPydantic(BaseModel):
    chunk_text: str = Field(description="Texte d'une partie (chunk) du document.")
    questions: list[QuestionPydantic] = Field(description="Liste des questions correspondant à ce chunk.")
    
class DocSummaryPydantic(BaseModel):
    doc_summary: str = Field(description="Résumé complet et structuré du contenu du document")
    doc_chunks: list[DocChunkPydantic] = Field(description="Liste des chunks du document.")

class DocQuestionsByChunkPydantic(BaseModel):
    doc_summary: str = Field(description="Résumé complet et structuré du contenu du document")
    doc_chunks: list[DocChunkPydantic] = Field(description="Liste des chunks du document.")

