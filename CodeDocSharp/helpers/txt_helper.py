import sys
import threading
import time
from helpers.python_helpers import staticproperty
from threading import Thread

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
    
    _activate_print = False    
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

    waiting_spinner_thread = None
    @staticmethod
    def print_with_spinner(text: str) -> Thread:
        if not txt.activate_print:
            return None
        
        # Ensure only one spinner thread is running at a time
        if txt.waiting_spinner_thread is not None and txt.waiting_spinner_thread.is_alive():
            txt.stop_spinner()

        txt.waiting_spinner_thread = Thread(target=txt.wait_spinner, args=(text,))
        txt.waiting_spinner_thread.daemon = True
        txt.waiting_spinner_thread.start()
        return txt.waiting_spinner_thread

    @staticmethod
    def wait_spinner(prefix):  # Optional prefix text
        # Spinner characters
        chars = "⠸⠼⠴⠦⠧⠇⠏⠋⠙⠹"

        txt.stop_animation = False
        while not txt.stop_animation:
            for char in chars:
                if txt.stop_animation:
                    break
                sys.stdout.write('\r' + prefix + ' ' + char + ' ')
                sys.stdout.flush()
                time.sleep(0.1)
                
    @staticmethod
    def stop_spinner():
        txt.stop_animation = True
        if txt.waiting_spinner_thread:
            txt.waiting_spinner_thread.join()
            txt.waiting_spinner_thread = None

    @staticmethod
    def stop_spinner_replace_text(text=None):
        if not txt.activate_print:
            return None

        empty = 80 * ' '
        
        if not text:
            text = empty
            sys.stdout.write(f'\r{empty}')
        else:
            text = '✓ ' + text
            sys.stdout.write(f'\r{empty}')
            sys.stdout.write(f'\r{text}\r\n')