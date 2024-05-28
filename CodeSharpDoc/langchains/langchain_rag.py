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
from langchain_chroma import Chroma
from langchain_community.embeddings.sentence_transformer import SentenceTransformerEmbeddings
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain_openai import OpenAIEmbeddings

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

# Obtain the vector store
def build_vectorstore(documents: List[str]):
    embeddings = OpenAIEmbeddings(openai_api_key= os.getenv("OPEN_API_KEY"))
    #embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
    chunks = []
    for document in documents:
        chunks.extend(split_text_into_chunks(document))
    db = Chroma.from_texts(texts= chunks, embedding = embeddings)
    return db

# Retrieve useful info similar to user query
def retrieve(llm: BaseChatModel, vectorstore, question) -> List[Document]:

    retriever_from_llm = MultiQueryRetriever.from_llm(
        retriever=vectorstore.as_retriever(), llm=llm
    )
    unique_docs = retriever_from_llm.get_relevant_documents(query=question)
    unique_docs = vectorstore.similarity_search(question)
    return unique_docs
    
def generate_response_from_retrieval(llm: BaseChatModel, retriever, question):
    template = f"""\
    # Instructions #
    Answer to the user question the best you can, only based on the context provided. Always give a full quote of the source(s) you used from the context to answer the question. 
    If none informations from the context seems relevant enough to answer the question properly, just answer: 'I didn't find any source of information relevant enough to answer the question properly'.
    
    # User Question #
    {question}
    
    # Context #
    """ + "{input}"
    rag_custom_prompt = ChatPromptTemplate.from_template(template)

    context = "\n".join(doc.page_content for doc in retriever)
    rag_chain = (
        rag_custom_prompt | llm | RunnablePassthrough()
    )
    answer = rag_chain.invoke(input= context)
    return answer