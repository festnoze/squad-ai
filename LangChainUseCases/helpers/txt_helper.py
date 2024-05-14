import json


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
            elif "output_text" in response:
                return response["output_text"]
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
        
    def extract_json_from_llm_response(response: any) -> str:
        content = txt.get_llm_answer_content(response)
        content = txt.get_code_block("json", content)
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
        
    def fix_invalid_json(json_str: str) -> str:
        if txt.validate_json(json_str):
            return json_str
        
        # embed into a json array
        json_str = '[' + json_str + ']'
        return json_str
            
    def validate_json(json_str: str) -> bool:
        try:
            json.loads(json_str)
            return True
        except json.JSONDecodeError as e:
            return False
        

    def indent(indent_level: int, code: str) -> str:
        indent_str = '    '
        lines = code.split('\n')
        ends_with_newline = False
        if lines[-1] == '': 
            lines = lines[:-1]
            ends_with_newline = True
        new_code = '\n'.join([indent_str * indent_level + line for line in lines])
        if ends_with_newline:
            new_code += '\n'
        return new_code
    
    def single_line(text: str) -> str:
        return ' '.join([line.strip() for line in text.split('\n')])
        
    def display_elapsed(start_time, end_time):
        elapsed_minutes = int((end_time - start_time) / 60)
        elapsed_seconds = int((end_time - start_time) % 60)
        print(f">> {elapsed_minutes}m {elapsed_seconds}s elapsed")

    def get_prop_or_key(object, prop_to_find):
        if hasattr(object, prop_to_find):
            return getattr(object, prop_to_find)
        elif isinstance(object, dict) and prop_to_find in object:
            return object[prop_to_find]
        else:
            return None