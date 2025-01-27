import json
import re
import sys
import time
from threading import Event, Thread
from typing import Optional, Union
from common_tools.helpers.python_helpers import staticproperty

class txt:    
    waiting_spinner_thread = None
    start_time: float = None
    stop_event = Event()
    
    @staticmethod
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
    
    @staticmethod
    def single_line(text: str) -> str:
        return ' '.join([line.strip() for line in text.split('\n')])

    @staticmethod  
    def get_elapsed_seconds(start_time, end_time) -> float:
        if not start_time or not end_time:
            return 0
        return float(end_time - start_time)
        
    @staticmethod
    def get_elapsed_str(elapsed_sec: float) -> str:
        elapsed_str = ''
        if not elapsed_sec: return ''
        elapsed_minutes = int(elapsed_sec / 60)
        if elapsed_minutes != 0:
            elapsed_seconds = int(elapsed_sec % 60)
        else:
            elapsed_seconds = round(float(elapsed_sec % 60), 2)
            seconds_int = int(elapsed_seconds)
            if seconds_int == 0:
                elapsed_seconds = round(elapsed_seconds, 3)
            elif seconds_int <= 9:
                elapsed_seconds = round(elapsed_seconds, 2)
            else:
                elapsed_seconds = round(elapsed_seconds, 1)

        if elapsed_minutes != 0:
            elapsed_str += f"{elapsed_minutes}m "
        elapsed_str +=  f"{elapsed_seconds}s"
        return '(' + elapsed_str + ')'
    
    @staticmethod
    def get_prop_or_key(object, prop_to_find):
        if hasattr(object, prop_to_find):
            return getattr(object, prop_to_find)
        elif isinstance(object, dict) and prop_to_find in object:
            return object[prop_to_find]
        else:
            return None
    
    _activate_print = False    
    @staticproperty
    def activate_print(cls):
        return cls._activate_print
    @activate_print.setter
    def activate_print(cls, value):
        cls._activate_print = value
    
    @staticmethod
    def print(text: str= "", end='\n'):
        if txt.activate_print and not txt.waiting_spinner_thread:
            print(text, end=end)

    @staticmethod
    def print_json(data, indent=0):
        """
        Recursively prints JSON data with indentation, handling nested structures.
        
        :param data: The JSON data to print (can be a dictionary or list)
        :param indent: The current level of indentation (default is 0)
        """
        if not txt.activate_print:
            return
        spacing = ' ' * indent
        
        # If data is a dictionary, iterate over key-value pairs
        if isinstance(data, dict):
            for key, value in data.items():
                txt.print(f"{spacing}'{key}':", end=" ")
                if isinstance(value, (dict, list)):
                    txt.print()  # Print a newline for clarity before nested items
                    txt.print_json(value, indent + 4)
                else:
                    txt.print(value)

        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    txt.print_json(item, indent + 4)
                else:
                    print(f"{spacing}-> {item}")

    @staticmethod
    def print_with_spinner(text: str) -> Thread:
        if not txt.activate_print:
            return None
        txt.start_time = time.time()

        # Ensure only one spinner thread is running at a time
        if txt.is_thread_spinner_alive():
            txt.stop_spinner()
            txt.print("Previous waiting spinner thread wasn't halted before creating a new one")

        txt.stop_event.clear()
        if not txt.waiting_spinner_thread:
            txt.waiting_spinner_thread = Thread(target=txt.wait_spinner, args=(text,))
        txt.waiting_spinner_thread.daemon = True
        txt.waiting_spinner_thread.start()
        return txt.waiting_spinner_thread

    @staticmethod
    def is_thread_spinner_alive():
        return txt.waiting_spinner_thread and txt.waiting_spinner_thread.is_alive()
    
    @staticmethod
    def to_python_case(text: str) -> str:
        return ''.join(['_' + c.lower() if c.isupper() else c for c in text]).lstrip('_')

    @staticmethod
    def wait_spinner(prefix):
        chars = "⠸⠼⠴⠦⠧⠇⠏⠋⠙⠹"
        while not txt.stop_event.is_set():
            for char in chars:
                if txt.stop_event.is_set():
                    break
                sys.stdout.write('\r' + prefix + ' ' + char + ' ')
                sys.stdout.flush()
                time.sleep(0.1)

    @staticmethod
    def stop_spinner():
        if txt.waiting_spinner_thread:
            # Signal the thread to stop
            txt.stop_event.set()

            # Wait for the thread to stop with a hard timeout of 5 seconds
            total_wait_time = 0
            interval = 0.1  # Check every 100ms
            while total_wait_time < 5.0:
                txt.waiting_spinner_thread.join(timeout=interval)
                if not txt.is_thread_spinner_alive():
                    break  # Exit the loop if the thread has stopped
                total_wait_time += interval

            # Final check if the thread is still alive
            if txt.is_thread_spinner_alive():
                print("Spinner Error: thread did not stop within 5 seconds. Forcing termination.")
            else:
                txt.waiting_spinner_thread = None  # Reset the reference if stopped

    @staticmethod
    def stop_spinner_replace_text(text=None)-> int:
        if not txt.activate_print:
            return None
        
        txt.stop_spinner()
        elapsed_str = None 
        elapsed_sec = None
        empty = 120 * ' '

        if not text:
            text = empty
            sys.stdout.write(f'\r{empty}')
            return 0
        else:
            if txt.start_time:
                elapsed_sec = txt.get_elapsed_seconds(txt.start_time, time.time())
                elapsed_str = txt.get_elapsed_str(elapsed_sec)
                if elapsed_str:
                    elapsed_str = f" {elapsed_str if elapsed_str else ''}."
                else:
                    elapsed_str = ''         
                txt.start_time = None

            text = f"✓ {text}{elapsed_str}" 
            sys.stdout.write(f'\r{empty}')
            sys.stdout.write(f'\r{text}\r\n')
            return elapsed_sec if elapsed_sec else 0
        
    @staticmethod
    def replace_text_continue_spinner(text=None):
        if not txt.activate_print:
            return None
        #txt.stop_spinner()
        empty = 120 * ' '
        sys.stdout.write(f'\r{empty}')
        if text:
            sys.stdout.write(f'\r{text}\r\n')
        #txt.start_spinner()
    
    @staticmethod    
    def remove_markdown(text):
        remove_chars = r"[*_#={}!]" # Miss markdown tags: |, +, -, ., (, ), [, ], <, >, ", ', `, ~, :, ;, ?, @, &, %, $, /, \
        return re.sub(remove_chars, "", text)
    
    @staticmethod
    def remove_commented_lines(content):
        content = '\n'.join([line for line in content.split('\n') if not line.strip().startswith('//')])
        return content    
    
    @staticmethod
    def apply_to_all_str(input: Optional[Union[str, dict, list]], delegate) -> Optional[Union[str, dict, list]]:
        """Apply a delegate function to all strings in a nested structure (str/dict/list)."""
        try:
            if isinstance(input, dict):
                return {key: txt.apply_to_all_str(value, delegate) for key, value in input.items()}
            elif isinstance(input, list):
                return [txt.apply_to_all_str(value, delegate) for value in input]
            elif isinstance(input, str):
                return delegate(input)
            else:
                return input
        except UnicodeDecodeError as e:
            print(f"Error while applying '{delegate.__name__}': {e}. In method: '{txt.apply_to_all_str.__name__}'")
            return input
    
    @staticmethod
    def fix_special_chars(input: Optional[Union[str, dict, list]]) -> Optional[Union[str, dict, list]]:
            input = txt.replace_unicode_special_chars(input)           
            input = txt.remove_html_tags(input)
            input = txt.handle_latin_encoding(input)
            return input
    
    @staticmethod
    def replace_unicode_special_chars(input: Optional[Union[str, dict, list]]) -> Optional[Union[str, dict, list]]:
        """Replace unicode special characters in a string/dictionary/list of strings."""
        def replace_unicode_special_chars_str(text: str) -> str:
            text = text.encode('utf-8').decode('unicode_escape')
            return text
            # try:
            #     return json.loads(f'"{text}"')
            # except json.JSONDecodeError as e:
            #     return text
        return txt.apply_to_all_str(input, replace_unicode_special_chars_str)
    
    @staticmethod
    def replace_unicode_special_chars_dict(input: dict) -> dict:
        text = json.dumps(input)
        text = txt.replace_unicode_special_chars(text)
        text = text.replace('\r', '\\r').replace('\n', '\\n').replace('\t', '\\t')
        return json.loads(text)
    
    @staticmethod
    def remove_html_tags(input: Optional[Union[str, dict, list]]) -> Optional[Union[str, dict, list]]:
        """Remove HTML tags from a string/dictionary/list of strings."""

        def remove_html_tags_str(text: str) -> str:
            # Define a list of HTML tags to be removed
            html_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br', 'blockquote', 'strong', 'span', 'em', 'i', 'b', 'u',
                        'a', 'img', 'code', 'pre', 'ul', 'ol', 'li', 'table', 'tr', 'td', 'th', 'tbody', 'thead', 'tfoot',
                        'div', 'section', 'article', 'aside', 'nav', 'header', 'footer', 'main', 'form', 'input', 'button',
                        'select', 'option', 'textarea', 'label', 'fieldset', 'legend', 'hr', 'sub', 'sup', 'small', 'big',
                        'del', 'ins', 's', 'strike', 'center', 'font', 'tt', 'kbd', 'samp', 'var', 'dfn', 'abbr', 'acronym',
                        'cite', 'q']

            # Remove all occurrences of tags, regardless of attributes
            for tag in html_tags:
                # Regex to remove opening tags with or without attributes
                text = re.sub(f'<{tag}[^>]*>', '', text, flags=re.IGNORECASE)
                # Regex to remove closing tags
                text = re.sub(f'</{tag}\\s*>', '', text, flags=re.IGNORECASE)

            # Replace common HTML entities like &nbsp;
            text = text.replace('&nbsp;', ' ').strip()
            return text

        return txt.apply_to_all_str(input, remove_html_tags_str)
    
    @staticmethod
    def handle_latin_encoding(input: Optional[Union[str, dict, list]]) -> Optional[Union[str, dict, list]]:
        """WORK? Handle latin special chars encoding converstion to UTF-8 from a string/dictionary/list of strings."""
        def handle_latin_encoding_str(text: str) -> str:
            try:
                return text.replace("’", "'").replace("œ", "oe").encode('latin1').decode('utf-8')
            except UnicodeDecodeError as e:
                return text
        return txt.apply_to_all_str(input, handle_latin_encoding_str)