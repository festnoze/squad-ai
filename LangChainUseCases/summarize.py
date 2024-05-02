from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.summarize import load_summarize_chain
from langchain.text_splitter import RecursiveCharacterTextSplitter

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
    def summarize_long_text(llm: BaseChatModel, text: str, max_tokens = 8000) -> str:
        num_tokens = llm.get_num_tokens(text)
        #print (f"There are {num_tokens} tokens in your file")
       
        text_splitter = RecursiveCharacterTextSplitter(separators=["\n\n", "\n", ". "], chunk_size=max_tokens, chunk_overlap=300)
        docs = text_splitter.create_documents([text])        
        #print (f"Initial document has been splitted into {len(docs)} documents")
        
        chain = load_summarize_chain(llm=llm, chain_type='map_reduce', verbose=False)
        result = chain.invoke(docs)
        
        answer: str
        if 'output_text' in result and result['output_text'] != '':
            answer = result['output_text']
        else:
            answer = result
        return answer