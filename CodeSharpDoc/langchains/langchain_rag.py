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

vectorstore_path = "./chroma_db"

def build_vectorstore(documents: List[dict], doChunkContent = True) -> any:
    embeddings = OpenAIEmbeddings(openai_api_key= os.getenv("OPEN_API_KEY"))
    #embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
    if doChunkContent:
        chunks = []
        for document in documents:
                chunks.extend(split_text_into_chunks(document['page_content']))                
        db = Chroma.from_texts(texts= chunks, embedding = embeddings, persist_directory= vectorstore_path)
    else:
        langchain_documents = [
            Document(page_content=doc["page_content"], metadata=doc["metadata"]) 
            for doc in documents
        ]
        db = Chroma.from_documents(documents= langchain_documents, embedding = embeddings, persist_directory= vectorstore_path)
    return db

def build_bm25_retriever(documents: List[str], doc_count: int) -> any:
    bm25_retriever = BM25Retriever.from_texts(documents)
    bm25_retriever.k = doc_count
    return bm25_retriever

def delete_vectorstore():
    file.delete_files_in_folder(vectorstore_path)

def load_vectorstore():
    embeddings = OpenAIEmbeddings(openai_api_key= os.getenv("OPEN_API_KEY"))
    return Chroma(persist_directory= vectorstore_path, embedding_function= embeddings)

# Retrieve useful info similar to user query
def retrieve(llm: BaseChatModel, vectorstore, question: str, additionnal_context: str = None, give_score = False) -> List[Document]:
    if additionnal_context:
        full_question = f"### User Question:\n {question}\n\n### Context:\n{additionnal_context}" 
    else:
        full_question = question

    #retriever_from_llm = MultiQueryRetriever.from_llm(retriever=vectorstore.as_retriever(), llm=llm)
    #results = retriever_from_llm.invoke(input==full_question)

    if give_score:
        results = vectorstore.similarity_search_with_score(full_question, k=2, filter={"functional_type": "Controller"})
    else:
        results = vectorstore.similarity_search(full_question, k=2, filter={"functional_type": "Controller"})
    return results
    
def generate_response_from_retrieval(llm: BaseChatModel, retrieved_docs, question: str) -> str:
    retrieval_prompt = file.get_as_str("prompts/rag_retriever_query.txt", remove_comments= True)
    retrieval_prompt = retrieval_prompt.replace("{question}", question)
    rag_custom_prompt = ChatPromptTemplate.from_template(retrieval_prompt)

    context = "• " + "\n• ".join(doc.page_content if type(doc) != tuple else doc[0].page_content for doc in retrieved_docs)
    rag_chain = rag_custom_prompt | llm | RunnablePassthrough()
    answer = rag_chain.invoke(input= context)
    return Llm.get_content(answer)