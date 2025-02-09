import re


class Helper:
    @staticmethod
    def convert_markdown(text):
        text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
        text = re.sub(r'__(.*?)__', r'_\1_', text)
        text = re.sub(r'^###\s*', '', text, flags=re.MULTILINE)
        return text
    
    @staticmethod
    def get_message_as_markdown_blocks(self, markdown_text):
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": markdown_text
                }
            }
        ]
        return blocks
    
    @staticmethod
    def iter_words_then_lines(response, line_delimiters=['.', ',', ':', ';', '!', '?', '\t', '\n'], switch_to_line_chunk_after_words_count=0, decode_unicode=True, buffer_size=1024):
        word_delimiters = line_delimiters + [' ']
        word_pattern = re.compile(r"[{}]".format(''.join(map(re.escape, word_delimiters))))
        line_pattern = re.compile(r"[{}]".format(''.join(map(re.escape, line_delimiters))))     
        buffer = ""
        chunk_count = 0
        use_line_chunk = False
        min_chars = 20
        
        for chunk in response.iter_content(chunk_size=buffer_size, decode_unicode=decode_unicode):
            if chunk:
                buffer += chunk                
                while True:
                    if use_line_chunk:
                        matches = list(line_pattern.finditer(buffer))
                    else:
                        matches = list(word_pattern.finditer(buffer))
                    
                    if not matches:
                        break
                    
                    last_match = matches[-1]  # Prendre le dernier match
                    chunk_count += 1
                    if not use_line_chunk and switch_to_line_chunk_after_words_count != 0 and chunk_count >= switch_to_line_chunk_after_words_count:
                        use_line_chunk = True
                    
                    if not use_line_chunk or len(buffer[:last_match.end()]) > min_chars:
                        yield buffer[:last_match.end()]
                    buffer = buffer[last_match.end():]
        
        if buffer and (not use_line_chunk or len(buffer) > min_chars):
            yield buffer
    