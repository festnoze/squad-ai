from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.output_parsers import StrOutputParser, ListOutputParser, MarkdownListOutputParser, JsonOutputParser
from langchain.schema.runnable import Runnable, RunnableParallel, RunnableSequence
from langchain.chains.base import Chain
from langchain.agents import AgentExecutor, create_tool_calling_agent, create_json_chat_agent, tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import yfinance as yf
from langchain_community.callbacks import get_openai_callback, OpenAICallbackHandler
#
import inspect
from typing import TypeVar, Generic, Any, Union

class Llm:
    @staticmethod
    def get_llm_answer_content(response: any) -> str:
        if isinstance(response, str):
            return response
        elif hasattr(response, 'content'):
            return response.content
        elif isinstance(response, dict):
            if "output" in response:
                return response["output"]
            elif "output_text" in response:
                return response["output_text"]
            elif "content" in response:
                return response["content"]
        return response
    
    @staticmethod
    def get_code_block(code_block_type: str, text: str) -> str:
        start_index = text.find(f"```{code_block_type}")
        end_index = text.rfind("```")        
        if start_index != -1 and end_index != -1 and start_index != end_index:
            return text[start_index + 3 + len(code_block_type):end_index].strip()
        else:
            return text
    
    @staticmethod
    def embed_into_code_block(code_block_type: str, text: str) -> str:
        return  f"```{code_block_type} \n{text}\n```\n"
        
    @staticmethod
    def extract_json_from_llm_response(response: any) -> str:
        content = Llm.get_llm_answer_content(response)
        content = Llm.get_code_block("json", content)
        start_index = -1 
        first_index_open_curly_brace = content.find('{')
        first_index_open_square_brace = content.find('[')
        last_index_close_curly_brace = content.rfind('}')
        last_index_close_square_brace = content.rfind(']')
        
        if first_index_open_curly_brace != -1:
            start_index = first_index_open_curly_brace
        if first_index_open_square_brace != -1 and (start_index == -1 or first_index_open_square_brace < start_index):
            start_index = first_index_open_square_brace

        if last_index_close_curly_brace != -1:
            end_index = last_index_close_curly_brace + 1
        if last_index_close_square_brace != -1 and (end_index == -1 or last_index_close_square_brace > end_index):
            end_index = last_index_close_square_brace + 1

        if start_index == -1 or end_index == -1:
            raise Exception("No JSON content found in response")
        
        return content[start_index:end_index]
    
    @staticmethod
    def invoke_llm_with_retry(llm: BaseChatModel, input: str = "", max_retries: int = 3):
        for i in range(max_retries):
            try:
                result = llm.invoke(input)
                return Llm.get_llm_answer_content(result)
            except Exception as e:
                print(f"Error: {e}")
                print(f"Retrying... {i+1}/{max_retries}")
        raise Exception(f"LLM failed. Stopped after {max_retries} retries")


    TPydanticModel = TypeVar('TPydanticModel', bound=BaseModel)    
    TOutputModel = TypeVar('TOutputModel')
    output_parser_instructions_name: str = 'output_parser_instructions'

    @staticmethod
    def get_chain_for_json_output_parser(llm: BaseChatModel, prompt_str: str, json_type: TPydanticModel, output_type: TOutputModel):
        assert issubclass(json_type, BaseModel), "json_type must inherit from BaseModel"
        assert inspect.isclass(output_type), "output_type must be a class"
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "Process the following input, then create a JSON object respecting those formating instructions: {" + Llm.output_parser_instructions_name + "}"),
                ("human", prompt_str),
            ]
        )    
        parser = JsonOutputParser(pydantic_object=json_type)
        chain = prompt | llm | parser
        return chain, parser.get_format_instructions()

    @staticmethod
    def invoke_parallel_prompts(llms_with_fallbacks: Union[BaseChatModel, list[BaseChatModel]], batch_size: int = None, *prompts: str) -> list[str]:        
        if not isinstance(llms_with_fallbacks, list):
            llms_with_fallbacks = [llms_with_fallbacks]
        chains = []
        for prompt in prompts:
            chain = ChatPromptTemplate.from_template(prompt) | llms_with_fallbacks[0]
            if len(llms_with_fallbacks) > 1:
                for llm_for_fallback in llms_with_fallbacks[1:]:
                    chain = chain.with_fallbacks(ChatPromptTemplate.from_template(prompt) | llm_for_fallback)
            chains.append(chain)
        answers = Llm._invoke_parallel_chains(None, batch_size, *chains)
        return answers

    @staticmethod
    def _invoke_parallel_chains(inputs: dict = None, batch_size: int = None, *chains: Chain) -> list[str]:
        if not batch_size:
            batch_size = len(chains)        
        if not inputs:
            inputs = {"input": ""}

        chains_batches = []
        for i in range(0, len(chains), batch_size):
            chains_batches.append(chains[i:i + batch_size])

        answers = []
        for chains_batch in chains_batches:
            combined = RunnableParallel(**{f"invoke_{i}": chain for i, chain in enumerate(chains_batch)})
            responses = combined.invoke(inputs)            
            responses_list = [responses[key] for key in responses.keys()]
            batch_answers = [Llm.get_llm_answer_content(response) for response in responses_list]
            answers.extend(batch_answers)

        return answers

    @staticmethod
    def invoke_llm_with_tools(llm: BaseChatModel, tools: list[any], input: str) -> str:
        #prompt = hub.pull("hwchase17/openai-tools-agent")
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You're a helpful AI assistant. You know which tools use to solve the given user problem."),
                ("human", "{input}"),
                MessagesPlaceholder("agent_scratchpad")
            ]
        )
        agent = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
        res = agent_executor.invoke({"input": input})
        return res["output"]

    @staticmethod
    def invoke_json_llm_with_tools(llm: BaseChatModel, tools: list[any], input: str) -> str:
        #prompt = hub.pull("hwchase17/openai-tools-agent")
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You're a helpful AI assistant. You know which tools use to solve the given user problem."),
                ("human", "{input}"),
                MessagesPlaceholder("agent_scratchpad")
            ]
        )
        
        agent = create_json_chat_agent(llm, tools, ChatPromptTemplate.from_messages([("human", "{input}")]))
        agent_executor = AgentExecutor(agent=agent, tools=tools)
        res = agent_executor.invoke({"input": input})
        return res["output"]
        
    def invoke_method_mesuring_openai_tokens_consumption(method_handler, *args, **kwargs):
        """
        Invokes the provided method handler within an OpenAI callback context 
        and displays the token consumption.
        
        Args:
            method_handler (callable): The method to be executed.
            *args: Variable length argument list for the method_handler.
            **kwargs: Arbitrary keyword arguments for the method_handler.
        """
        with get_openai_callback() as openai_callback:
            method_handler(*args, **kwargs)
            Llm.display_tokens_consumption(openai_callback)

    def get_eur_usd_rate():
        ticker = yf.Ticker("EURUSD=X")
        data = ticker.history(period="1d")
        rate = data["Close"].iloc[-1]
        return rate
    
    def display_tokens_consumption(cb: OpenAICallbackHandler):
        max_len = max(len(str(cb.completion_tokens)), len(str(cb.prompt_tokens)), len(str(cb.total_tokens))) + 2
        cost_eur = cb.total_cost / Llm.get_eur_usd_rate()
        print("Token consumption:")
        print(f"Input prompt: {cb.prompt_tokens}")
        print(f"Completion: + {cb.completion_tokens}")    
        print(f"            " + "-" * max_len)
        print(f"Total tokens: {cb.total_tokens}")
        print(f"Total cost:   {cost_eur:.3f}€ ({cb.total_cost:.3f}$)")
        if cb.total_tokens > 0:
            print(f"(Cost by 1M tokens: {(1000000 * cb.total_cost / cb.total_tokens):.3f}$)\n") 
        