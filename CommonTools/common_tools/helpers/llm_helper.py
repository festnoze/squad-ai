import asyncio
import json
import time
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field
from langchain_core.output_parsers import StrOutputParser, ListOutputParser, MarkdownListOutputParser, JsonOutputParser, BaseTransformOutputParser
from langchain_core.runnables import Runnable, RunnableParallel, RunnableSequence
from langchain.chains.base import Chain
from langchain.agents import AgentExecutor, create_tool_calling_agent, create_json_chat_agent, tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.callbacks import get_openai_callback, OpenAICallbackHandler
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from common_tools.helpers.txt_helper import txt
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.helpers.execute_helper import Execute
import inspect
from typing import AsyncGenerator, TypeVar, Union

class Llm:
    # Constants 
    new_line_for_stream_over_http = "\\/%*/\\" # use specific new line conversion over streaming, as new line is handled differently across platforms
    generic_tag = "\\/%*TAG%*/\\" # use specific tag to erase previous stream content
    erase_all_previous_stream_tag = generic_tag.replace('TAG', 'EraseAllPrevious')
    erase_single_previous_stream_tag = generic_tag.replace('TAG', 'eraseSinglePreviousChunk')

    @staticmethod
    def get_content(response: any) -> str:
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
    async def invoke_prompt_with_fallback_async(action_name: str, llms_with_fallbacks: Union[Runnable, list[Runnable]], prompt: Union[str, ChatPromptTemplate]) -> list[str]:
        """Invoke single LLM w/o output parser, nor batching, nor parallel multiple prompts (fallbacks possible)"""
        answers = await Llm.invoke_parallel_prompts_async(action_name, llms_with_fallbacks, *[prompt])
        return answers[0]
    
    @staticmethod
    async def invoke_chain_with_input_async(action_name: str = "", chain: Chain = None, input: dict = None) -> list[str]:       
        if not input: input = {"input": ""}
        chain_w_config = chain.with_config({"run_name": f"{action_name}"})
        return await chain_w_config.ainvoke(input)  
     
    # @staticmethod
    # def invoke_prompt_with_output_parser_and_fallbacks(action_name: str, llms_with_fallbacks: Union[Runnable, list[Runnable]], prompt: Union[str, ChatPromptTemplate], output_parser: BaseTransformOutputParser = None, batch_size:int = None) -> list[str]:
    #     """Invoke a single LLM prompt (fallbacks, output parser, batching possible in option, no parallel multiple prompts)"""
    #     return Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks(action_name, llms_with_fallbacks, output_parser, batch_size, *[prompt])
    
    @staticmethod
    async def invoke_parallel_prompts_async(action_name: str, llms_with_fallbacks: Union[Runnable, list[Runnable]], *prompts: Union[str, ChatPromptTemplate]) -> list[str]:
        """Invoke LLM in parallel, w/o output parser, nor batching (fallbacks possible)"""
        return await Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async(action_name, llms_with_fallbacks, None, None, *prompts)
   
    # @staticmethod
    # def invoke_parallel_prompts_with_parser_batchs_fallbacks(action_name: str, llms_with_fallbacks: Union[Runnable, list[Runnable]], output_parser: BaseTransformOutputParser, batch_size: int = None, *prompts: Union[str, ChatPromptTemplate]) -> list[str]:
    #     return Execute.async_wrapper_to_sync(Llm.invoke_parallel_prompts_with_parser_batchs_fallbacks_async, action_name, llms_with_fallbacks, output_parser, batch_size, *prompts)
    
    @staticmethod
    async def invoke_parallel_prompts_with_parser_batchs_fallbacks_async(action_name: str, llms_with_fallbacks: Union[Runnable, list[Runnable]], output_parser: BaseTransformOutputParser, batch_size: int = None, *prompts: Union[str, ChatPromptTemplate]) -> list[str]:
        if len(prompts) == 0:
            return []        
        if not isinstance(llms_with_fallbacks, list):
            llms_with_fallbacks = [llms_with_fallbacks]
        chains = []
        for prompt in prompts:
            # create chain out of str prompt transformed to  ChatPromptTemplate and specified LLM
            chain = Llm.prompt_as_chat_prompt_template(prompt) | llms_with_fallbacks[0]
            # add output parser to the chain if specified
            if output_parser: chain = chain | output_parser

            # add fallbacks to the chain if more than one LLMs are specified
            if len(llms_with_fallbacks) > 1:
                fallback_chains = []
                for llm_for_fallback in llms_with_fallbacks[1:]:
                    fallback_chain = Llm.prompt_as_chat_prompt_template(prompt) | llm_for_fallback
                    if output_parser: fallback_chain = fallback_chain | output_parser
                    fallback_chains.append(fallback_chain)
                chain = chain.with_fallbacks(fallback_chains)
            chains.append(chain)

        # If output parser is JsonOutputParser, add the instructions to the input
        inputs = None
        if output_parser and isinstance(output_parser, JsonOutputParser):
            inputs = {Llm.output_parser_instructions_name: output_parser.get_format_instructions()}
        
        answers = await Llm._invoke_parallel_chains_async(action_name, inputs, batch_size, *chains)
        return answers
        
    # @staticmethod
    # def _invoke_parallel_chains(action_name: str = "", inputs: dict = None, batch_size: int = None, *chains: Chain) -> list[str]:
    #     Execute.async_wrapper_to_sync(Llm._invoke_parallel_chains_async, action_name, inputs, batch_size, *chains)
    
    @staticmethod
    async def _invoke_parallel_chains_async(action_name: str = "", inputs: dict = None, batch_size: int = None, *chains: Chain) -> list[str]:
        if len(chains) == 0:
            return []
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
            parallel_chains = combined.with_config({"run_name": f"{action_name}{f"- batch x{str(batch_size)}" if (batch_size and len(chains_batches)>1) else ""}"})
            responses = await parallel_chains.ainvoke(inputs) #TODO: try replace by: abatch

            responses_list = [responses[key] for key in responses.keys()]
            batch_answers = [Llm.get_content(response) for response in responses_list]
            answers.extend(batch_answers)
        return answers    
    
    @staticmethod
    async def invoke_llm_with_tools_async(llm_or_chain: Runnable, tools: list[any], input: str) -> str:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You're a helpful AI assistant. You know which tools use to solve the given user problem."),
                ("human", "{input}"),
                MessagesPlaceholder("agent_scratchpad")
            ]
        )
        agent = create_tool_calling_agent(llm_or_chain, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
        res = await agent_executor.ainvoke({"input": input})
        return res["output"]

    @staticmethod
    async def invoke_json_llm_with_tools_async(llm_or_chain: Runnable, tools: list[any], input: str) -> str:
        #prompt = hub.pull("hwchase17/openai-tools-agent")
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You're a helpful AI assistant. You know which tools use to solve the given user problem."),
                ("human", "{input}"),
                MessagesPlaceholder("agent_scratchpad")
            ]
        )
        
        agent = create_json_chat_agent(llm_or_chain, tools, ChatPromptTemplate.from_messages([("human", "{input}")]))
        agent_executor = AgentExecutor(agent=agent, tools=tools)
        res = await agent_executor.ainvoke({"input": input})
        return res["output"]
    
    @staticmethod
    async def invoke_as_async_stream(action_name:str, llm_or_chain: Runnable, input, display_console: bool = False, content_chunks:list[str] = None, does_stream_across_http: bool = False):
        if not content_chunks: content_chunks = []
        has_content_prop:bool = None
        
        llm_or_chain_w_config = llm_or_chain.with_config({"run_name": f"{action_name}"})

        async for chunk in llm_or_chain_w_config.astream(input):
            # Analyse specific stream structure upon first chunk: Handle both OpenAI & Ollama types
            if not has_content_prop:
                if hasattr(chunk, 'content'): #LangChainAdapterType.OpenAI
                    has_content_prop = True
                elif isinstance(chunk, str): #LangChainAdapterType.Ollama
                    has_content_prop = False
                else:
                    raise ValueError(f"Unknown stream structure: neither OpenAI nor Ollama")
            
            content = chunk if not has_content_prop else chunk.content
            
            if display_console:
                print(content, end= "", flush= True)
            if content is not None and content != '':
                content_chunks.append(content)
                content = content.replace('\r\n', '\n')
                if does_stream_across_http:
                    content = content.replace('\n', Llm.new_line_for_stream_over_http)
                yield content.encode('utf-8')
            else:
                pass

    @staticmethod
    def prompt_as_chat_prompt_template(prompt: Union[str, ChatPromptTemplate]) -> ChatPromptTemplate:
        if isinstance(prompt, ChatPromptTemplate):
            return prompt
        return ChatPromptTemplate.from_messages([HumanMessage(prompt)])
    
    @staticmethod
    def extract_json_from_llm_response(response: any) -> str:
        content = Llm.get_content(response)
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
        
        content = content[start_index:end_index]
        try:
            result = json.loads(content)
            return result
        except Exception as e:
            raise Exception(f"Error extracting JSON from content: '{content[:200]}...'.\nError: {e}")
    
    TPydanticModel = TypeVar('TPydanticModel', bound=BaseModel)    
    TOutputModel = TypeVar('TOutputModel')
    output_parser_instructions_name: str = 'output_parser_instructions'

    @staticmethod
    def get_prompt_and_json_output_parser(prompt_str: str, json_type: TPydanticModel, output_type: TOutputModel):
        assert issubclass(json_type, BaseModel), "provided pydantic type must inherit from BaseModel"
        assert inspect.isclass(output_type), "output_type must be a class"
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "Process the following input, then create a JSON object respecting those formating instructions: {" + Llm.output_parser_instructions_name + "}"),
                ("human", prompt_str),
            ]
        )    
        parser = JsonOutputParser(pydantic_object=json_type)
        return prompt, parser
        
    def call_method_mesuring_openai_tokens_consumption(method_handler, *args, **kwargs):
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
    
    def display_tokens_consumption(cb: OpenAICallbackHandler):
        max_len = len(Llm.format_number(cb.total_tokens)) + 2
        cost_eur = cb.total_cost / Llm.get_eur_usd_rate()
        print("Token consumption:")
        print(f"Input prompt: {Llm.format_number(cb.prompt_tokens)}")
        print(f"rewritting: + {Llm.format_number(cb.rewritting_tokens)}")    
        print(f"            " + "-" * max_len)
        print(f"Total tokens: {Llm.format_number(cb.total_tokens)}")
        print(f"Total cost:   {cost_eur:.3f}€ ({cb.total_cost:.3f}$)")
        if cb.total_tokens != 0:
            print(f"(Cost by 1M tokens: {(1000000 * cb.total_cost / cb.total_tokens):.3f}$)\n") 
    
    def format_number(number: int) -> str:
        return "{:,}".format(number).replace(",", " ")
    
    
    @staticmethod
    def get_text_from_chunks(chunks: list) -> str:
        """Concatenate a list of text chunks into a single string."""
        isBinary = any(chunks) and isinstance(chunks[0], bytes)
        if isBinary:
            chunks = [chunk.decode('utf-8').replace(Llm.new_line_for_stream_over_http, '\n') for chunk in chunks]
        else:
            chunks = [chunk['text'] if 'text' in chunk else chunk for chunk in chunks]
        return ''.join(chunks)
    
    @staticmethod
    async def write_static_text_as_stream(text: str, interval_btw_words: float = 0.07) -> AsyncGenerator[str, None]:
        words = text.split(" ")
        for word in words:
            yield f"{word} "
            await asyncio.sleep(interval_btw_words)

    @staticmethod    
    async def remove_all_previous_stream_async(remove_word_byword: bool = True, words_count_to_remove: int = 20):        
        if not remove_word_byword:
            # Remove all previous text at once
            yield Llm.erase_all_previous_stream_tag + ' '
        else:
            # Remove waiting message word by word
            remove_text = (Llm.erase_single_previous_stream_tag + ' ') * words_count_to_remove
            async for chunk in Llm.write_static_text_as_stream(remove_text[:-1]): # remove the last space!
                yield chunk

    @staticmethod       
    def test_llm_inference(llm:BaseChatModel) -> float:
        model_name = llm.model_name if hasattr(llm, 'model_name') else llm.model if hasattr(llm, 'model') else llm.__class__.__name__
        txt.print(f"> Testing inference for model: {model_name} LLM")
        start_time = time.time()
        try:
            answer = llm.invoke("quelles étaient les capitales de la CEE ?")
        except Exception as e:
            txt.print(f"/!\\ Inference test failed for model: '{model_name}'/!\\: {e}")
            return 0.0
        
        elapsed_time = time.time() - start_time
        txt.print(f"- Inference test succeed for model: '{model_name}' in {elapsed_time:.2f}s. \nModel response: '{Llm.get_content(answer)[:200]}...'.")
        return elapsed_time

    @staticmethod        
    async def test_llm_inference_streaming_async(llm:BaseChatModel) -> float:
        model_name = llm.model_name if hasattr(llm, 'model_name') else llm.model if hasattr(llm, 'model') else llm.__class__.__name__
        txt.print(f"> Testing inference as async streaming for model: {model_name}")
        start_time = time.time()
        try:
            answer = ''
            async for chunk in llm.astream("quelles sont les capitales de la CEE ?"):
                answer += chunk.content
        except Exception as e:
            txt.print(f"/!\\ Inference test failed for model: '{model_name}'/!\\: {e}")
            return 0.0
        
        elapsed_time = time.time() - start_time
        txt.print(f"- Streaming async inference test succeed for model: '{model_name}' in {elapsed_time:.2f}s. \nModel response: '{Llm.get_content(answer)[:200]}...'.")
        return elapsed_time