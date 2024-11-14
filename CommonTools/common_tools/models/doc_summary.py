from typing import Union
from pydantic import BaseModel, Field
import pandas as pd
from common_tools.helpers.txt_helper import txt


class Question:
    def __init__(self, text: str = ''):
        self.text = text

    def __repr__(self) -> str:
        return f"Question: {self.text})"

class DocChunk:
    def __init__(self, text: str = '', questions:list[Question] = []):
        self.text = text
        self.questions = questions
    
    def __repr__(self) -> str:
        return f"DocChunk: {self.text})"
    
class DocSummary:
    def __init__(self, doc_content: str = None, doc_summary: str = None, doc_chunks_with_questions: Union[dict, list[DocChunk]] = None, **kwargs):
        if kwargs:
            self.doc_content:str = kwargs.get('doc_content', doc_content)
            self.doc_summary:str = kwargs.get('doc_summary', doc_summary)
            self.doc_chunks:list[DocChunk] = self.get_typed_chunks_with_their_questions(kwargs.get('doc_chunks', doc_chunks_with_questions))
        else:
            self.doc_content:str = doc_content
            self.doc_summary:str = doc_summary
            self.doc_chunks:list[DocChunk] = self.get_typed_chunks_with_their_questions(doc_chunks_with_questions)
    
    def get_typed_chunks_with_their_questions(self, chunks_and_questions_dict: Union[dict, list[DocChunk]]) -> list[DocChunk]:
        chunks_with_questions_typed = [] 
        if isinstance(chunks_and_questions_dict, list) and any(chunks_and_questions_dict) and isinstance(chunks_and_questions_dict[0], DocChunk):
            return chunks_and_questions_dict
        for chunk_with_questions in chunks_and_questions_dict:
            questions = chunk_with_questions['questions']
            question_list = []
            if any(questions) and isinstance(questions[0], Question):
                question_list = questions
            else:
                for question in questions:
                    question_list.append(Question(question))
                
            doc_chunk = DocChunk(chunk_with_questions['text'], question_list)
            chunks_with_questions_typed.append(doc_chunk)      
        return chunks_with_questions_typed
    
    def display_to_terminal_pandas(self):
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

    def display_to_terminal(self, display_questions: bool = True):
        i = 1
        total_questions = 0
        max_questions = 0
        total_chunks = len(self.doc_chunks)
        for chunk in self.doc_chunks:
            txt.print(f'\n>>> Chunk n°{i}:\n' + chunk.text)
            if len(chunk.questions) > max_questions: 
                max_questions = len(chunk.questions)
            i += 1
            if display_questions:
                j = 1
                for question in chunk.questions:
                    txt.print(f'>> Question n°{str(j)}: {question.text}')
                    total_questions += 1
                    j += 1
        txt.print(f'Total: {total_chunks} chunks')
        txt.print(f'Total: {total_questions} questions')
        txt.print(f'Max.: {max_questions} questions')
        txt.print(f'Average: {total_questions/total_chunks:.1f} questions by chunk')
        txt.print(f'All chunks size: {sum([len(chunk.text.split(' ')) for chunk in self.doc_chunks])} words.')

#################
# Pydantic models
#################
class QuestionPydantic(BaseModel):
    text: str = Field(description="Une question atomique et complète portant sur une partie du chunk du document.")

class DocChunkPydantic(BaseModel):
    text: str = Field(description="Texte d'une partie (chunk) du document.")
    questions: list[QuestionPydantic] = Field(description="Liste des questions correspondant à ce chunk.")
    
class DocSummaryPydantic(BaseModel):
    doc_summary: str = Field(description="Résumé complet et structuré du contenu du document")
    doc_chunks: list[DocChunkPydantic] = Field(description="Liste des chunks du document.")

class DocQuestionsByChunkPydantic(BaseModel):
    doc_summary: str = Field(description="Résumé complet et structuré du contenu du document")
    doc_chunks: list[DocChunkPydantic] = Field(description="Liste des chunks du document.")

