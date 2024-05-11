class txt:
    @staticmethod
    def get_content(response: any) -> str:
        if hasattr(response, 'content'):
            content = response.content
        else:
            content = response
        return content
    
    def get_code_block(code_block_type: str, text: str) -> str:
        start_index = text.find(f"```{code_block_type}")
        end_index = text.rfind("```")        
        if start_index != -1 and end_index != -1 and start_index != end_index:
            return text[start_index + 3 + len(code_block_type):end_index].strip()
        else:
            return text