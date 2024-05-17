from langchain_community.embeddings.openai import OpenAIEmbeddings
from langchain_core.embeddings import Embeddings
from langchain_core.pydantic_v1 import Field, root_validator


from langchain.text_splitter import CharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_community.callbacks import get_openai_callback, OpenAICallbackHandler

# Convert txt into chunks 
def chunkify_txt(txt):

    txt_splitter = CharacterTextSplitter(
        separator= "\n",
        chunk_size= 1000,
        chunk_overlap= 200,
        length_function= len
    )

    chunks = txt_splitter.split_text(txt)

    return chunks

## Obtain the vector store
def get_vector(chunks):
    embeddings = OpenAIEmbeddings()

    vectorstore = FAISS.from_texts(texts= chunks, embedding = embeddings)

    return vectorstore

## Retrieve useful info similar to user query
def retrieve(vectorstore, question):
    logging.basicConfig()
    logging.getLogger("langchain.retrievers.multi_query").setLevel(logging.INFO)

    retriever_from_llm = MultiQueryRetriever.from_llm(
        retriever=vectorstore.as_retriever(), llm=ChatOpenAI(temperature=0)
    )
    unique_docs = retriever_from_llm.get_relevant_documents(query=question)
    
    print(f"Number of unique documents retrieved: {len(unique_docs)}")
    
    return unique_docs
    

## Generate response for user query

def gen_resp(retriever, question):
    llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0)
    template = """... [custom prompt template] ..."""
    rag_custom_prompt = PromptTemplate.from_template(template)

    context = "\n".join(doc.page_content for doc in retriever)

    rag_chain = (
        {"context": context, "question": RunnablePassthrough()} | rag_custom_prompt | llm
    )

    answer = rag_chain.invoke(question)

    return answer