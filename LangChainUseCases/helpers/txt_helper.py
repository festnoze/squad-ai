class txt:
    @staticmethod
    def get_llm_answer_content(response: any) -> str:
        if isinstance(response, str):
            return response
        elif hasattr(response, 'content'):
            return response.content
        elif isinstance(response, dict):
            if "output" in response:
                return response["output"]
            elif "content" in response:
                return response["content"]
        return response
    
    def get_code_block(code_block_type: str, text: str) -> str:
        start_index = text.find(f"```{code_block_type}")
        end_index = text.rfind("```")        
        if start_index != -1 and end_index != -1 and start_index != end_index:
            return text[start_index + 3 + len(code_block_type):end_index].strip()
        else:
            return text
        
    def indent(indent_level: int, code: str) -> str:
        indent_str = "\t"
        return '\n'.join([indent_str * indent_level + line for line in code.split('\n')])