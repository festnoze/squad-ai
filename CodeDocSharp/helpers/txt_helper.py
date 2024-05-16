import sys
import threading
import time
from helpers.python_helpers import staticproperty


class txt:
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
    
    _activate_print = True
    
    @staticproperty
    def activate_print(cls):
        return cls._activate_print

    @activate_print.setter
    def activate_print(cls, value):
        cls._activate_print = value
    
    @staticmethod
    def print(text: str):
        if txt.activate_print:
            print(text)

    def print_with_spinner(text: str):
        if txt.activate_print == False:
            return None
        
        thread = threading.Thread(target=txt.wait_spinner, args=(text,))
        thread.daemon = True
        thread.start()
        return thread

    stop_animation = True
    def wait_spinner(prefix):  # Optional prefix text
        chars = "-\|/"
        txt.stop_animation = False
        while not txt.stop_animation:
            for char in chars:
                sys.stdout.write('\r' + prefix + ' ' + char + ' ')
                sys.stdout.flush()
                time.sleep(0.5)

    def stop_spinner(thread, text=None):
        if txt.activate_print == False:
            return None
        if not text:
            text = 50 * ' '
        sys.stdout.write(f'\r{text}\n')
        sys.stdout.flush()
        txt.stop_animation = True
        thread.join()
