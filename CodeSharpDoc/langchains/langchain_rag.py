import os
from helpers.file_helper import file
from typing import List
from langchain_community.embeddings.openai import OpenAIEmbeddings
from langchain_core.embeddings import Embeddings
from langchain_core.pydantic_v1 import Field, root_validator

# RAG imports
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document
#from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever
from langchain_chroma import Chroma
from langchain_community.embeddings.sentence_transformer import SentenceTransformerEmbeddings
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain_openai import OpenAIEmbeddings

from helpers.llm_helper import Llm
from models.question_analysis import QuestionAnalysis

def split_text_into_chunks(text: str) -> List[str]:
    txt_splitter = CharacterTextSplitter(
        separator= "\n",
        chunk_size= 8000,
        chunk_overlap= 200,
        length_function= len
    )
    chunks = txt_splitter.split_text(text)
    return chunks

def build_vectorstore_from_folder_files(folder_path: str):
    txt_loader = TextLoader()
    documents = txt_loader.load(folder_path)
    return build_vectorstore(documents)

vectorstore_chroma_db_path = "./chroma_db"

def build_vectorstore(documents: List[dict], doChunkContent = True) -> any:
    if not documents or len(documents) == 0:
        return None
        
    embeddings = OpenAIEmbeddings(openai_api_key= os.getenv("OPEN_API_KEY"))
    #embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
    if doChunkContent:
        chunks = []
        for document in documents:
                chunks.extend(split_text_into_chunks(document['page_content']))                
        db = Chroma.from_texts(texts= chunks, embedding = embeddings, persist_directory= vectorstore_chroma_db_path)
    else:
        langchain_documents = [
            Document(page_content=doc["page_content"], metadata=doc["metadata"]) 
            for doc in documents
        ]
        db = Chroma.from_documents(documents= langchain_documents, embedding = embeddings, persist_directory= vectorstore_chroma_db_path)
    return db

def build_bm25_retriever(documents: List[Document], k: int) -> any:
    bm25_retriever = BM25Retriever.from_documents(documents)
    bm25_retriever.k = k
    return bm25_retriever

def delete_vectorstore_files():
    file.delete_files_in_folder(vectorstore_chroma_db_path)

def load_vectorstore():
    embeddings = OpenAIEmbeddings(openai_api_key= os.getenv("OPEN_API_KEY"))
    return Chroma(persist_directory= vectorstore_chroma_db_path, embedding_function= embeddings)

# Retrieve useful info similar to user query
def retrieve(llm: BaseChatModel, vectorstore, question: str, additionnal_context: str = None, filters: dict = None, give_score: bool = False, max_retrived_count: int = 10, min_score: float = None, min_retrived_count: int = None) -> List[Document]:
    if additionnal_context:
        full_question = f"### User Question:\n {question}\n\n### Context:\n{additionnal_context}" 
    else:
        full_question = question

    #retriever_from_llm = MultiQueryRetriever.from_llm(retriever=vectorstore.as_retriever(), llm=llm)
    #results = retriever_from_llm.invoke(input==full_question)

    if give_score:
        results = vectorstore.similarity_search_with_score(full_question, k=max_retrived_count, filter=filters)
        if min_retrived_count and min_score and min_retrived_count > len(results):
            lim_res = []
            for result in results:
                if isinstance(result, tuple) and result[1] >= min_score or len(lim_res) < min_retrived_count:
                    lim_res.append(result)
            results = lim_res
    else:
        results = vectorstore.similarity_search(full_question, k=max_retrived_count, filter=filters)
    return results
    
def generate_response_from_retrieved_chunks(llm: BaseChatModel, retrieved_docs: list[Document], questionAnalysis: QuestionAnalysis) -> str:
    retrieval_prompt = file.get_as_str("prompts/rag_retriever_query.txt", remove_comments= True)
    retrieval_prompt = retrieval_prompt.replace("{question}", questionAnalysis.translated_question)
    additional_instructions = ''
    if not questionAnalysis.detected_language.__contains__("english"):
        additional_instructions = file.get_as_str("prompts/rag_prefiltering_ask_for_translation_instructions.txt", remove_comments= True)
        additional_instructions = additional_instructions.replace("{target_language}", questionAnalysis.detected_language)
    retrieval_prompt = retrieval_prompt.replace("{additional_instructions}", additional_instructions)
    rag_custom_prompt = ChatPromptTemplate.from_template(retrieval_prompt)

    context = get_str_from_rag_retrieved_docs(retrieved_docs)
    rag_chain = rag_custom_prompt | llm | RunnablePassthrough()
    answer = rag_chain.invoke(input= context)
    return Llm.get_content(answer)

@staticmethod
def get_str_from_rag_retrieved_docs(retrieved_docs):
    context = ''
    for retrieved_doc in retrieved_docs:
        doc = retrieved_doc[0] if isinstance(retrieved_doc, tuple) else retrieved_doc
        summary = doc.page_content
        functional_type = doc.metadata.get('functional_type')
        method_name = doc.metadata.get('method_name')
        namespace = doc.metadata.get('namespace')
        struct_name = doc.metadata.get('struct_name')
        struct_type = doc.metadata.get('struct_type')

        context += f"• {summary}. In {functional_type.lower()} {struct_type.lower()}  '{struct_name}',{" method '" + method_name + "'," if method_name else ''} from namespace '{namespace}'.\n"
    return context