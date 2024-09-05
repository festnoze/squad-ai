import os
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
from langchain_community.vectorstores import FAISS
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain_openai import OpenAIEmbeddings

def chunkify_docs(documents) -> List[dict]:
    txt_splitter = CharacterTextSplitter(
        separator= "\n",
        chunk_size= 8000,
        chunk_overlap= 200,
        length_function= len
    )
    chunks = txt_splitter.split_documents(documents)
    return chunks

## Obtain the vector store
def build_vectorstore(documents: List[str]):
    embeddings = OpenAIEmbeddings(openai_api_key= os.getenv("OPEN_API_KEY"))
    chunks = chunkify_docs(documents)
    vectorstore = FAISS.from_texts(texts= chunks, embedding = embeddings)
    return vectorstore

## Retrieve useful info similar to user query
def retrieve(llm: BaseChatModel, vectorstore, question) -> List[Document]:

    retriever_from_llm = MultiQueryRetriever.from_llm(
        retriever=vectorstore.as_retriever(), llm=llm
    )
    unique_docs = retriever_from_llm.get_relevant_documents(query=question)
    
    print(f"Number of unique documents retrieved: {len(unique_docs)}")    
    return unique_docs
    
def generate_response_from_retrieval(llm: BaseChatModel, retriever, question):
    template = """... [custom prompt template] ..."""
    rag_custom_prompt = ChatPromptTemplate.from_template(template)

    context = "\n".join(doc.page_content for doc in retriever)
    rag_chain = (
        {"context": context, "question": RunnablePassthrough()} | rag_custom_prompt | llm
    )
    answer = rag_chain.invoke(question)
    return answer