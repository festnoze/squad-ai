from typing import List
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.summarize import load_summarize_chain
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from helpers.txt_helper import txt

class Summarize:
    @staticmethod
    def summarize_short_text(llm: BaseChatModel, text: str) -> str:
        instructions = "Please summarize the following piece of text. Respond in a manner that a 5 year old would understand."
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", instructions),
                ("human", "{input}"),
            ]
        )
        result = llm.invoke(input=text)
        return result
        
    @staticmethod
    def split_text(llm: BaseChatModel, text: str, max_tokens = 8000) -> List[Document]:
        num_tokens = llm.get_num_tokens(text)
        if num_tokens <= max_tokens:
            return [Document(text)]
        
        text_splitter = RecursiveCharacterTextSplitter(separators=["\n\n", "\n", ". "], chunk_size=max_tokens, chunk_overlap=300)
        docs = text_splitter.create_documents([text])
        return docs
    
    @staticmethod
    def splitting_chain(llm):
        chain = load_summarize_chain(llm=llm, chain_type='map_reduce', verbose=False)
        return chain
    
    @staticmethod
    def split_prompt_and_invoke(llm: BaseChatModel, text: str, max_tokens = 8000) -> str:
        docs = Summarize.split_text(llm, text, max_tokens)
        chain = Summarize.splitting_chain(llm)
        result = chain.invoke(docs)        
        return txt.get_llm_answer_content(result)