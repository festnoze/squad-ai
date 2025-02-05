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
    def iter_words(response, delimiters=[' ', '.', ',', ':', ';', '!', '?'], decode_unicode=True, buffer_size=1024):
        pattern = re.compile(r"[{}]".format(''.join(map(re.escape, delimiters))))        
        buffer = ""
        for chunk in response.iter_content(chunk_size=buffer_size, decode_unicode=decode_unicode):
            if chunk:
                buffer += chunk                
                while True:# Process the buffer as long as a delimiter is found.
                    match = pattern.search(buffer)
                    if not match:
                        break
                    yield buffer[:match.end()] # Yield the data until the delimiter.
                    buffer = buffer[match.end():] # Remove the yielded part with the delimiter from the buffer.
        if buffer:
            yield buffer
    