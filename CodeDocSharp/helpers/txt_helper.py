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

    waiting_spinner_thread: Thread = None
    def print_with_spinner(text: str) -> Thread:
        if txt.activate_print == False:
            return None
        
        while txt.waiting_spinner_thread is not None:
            if not txt.waiting_spinner_thread.is_alive():
                txt.waiting_spinner_thread = None

        waiting_spinner_thread = Thread(target=txt.wait_spinner, args=(text,))
        waiting_spinner_thread.daemon = True
        waiting_spinner_thread.start()
        return waiting_spinner_thread

    stop_animation = True
    def wait_spinner(prefix):  # Optional prefix text
        #chars = "-\|/"
        #chars = "⢄⢂⢁⡁⡈⡐⡠⢠⢰⢸⣸⣴⣼⣾⣿"
        #chars = "⠈⠐⠠⢀⡀⠄⠂⠅⡁⡈⡐⡠"
        #chars = "⠄⠆⠖⠶⡶⣶⣷⣧⣩⣉⠉⠈"
        #chars = "⠟⠯⠷⠾⠽⠻⠹⠸⠼⠴⠦⠧⠇⠏"
        chars = "⠸⠼⠴⠦⠧⠇⠏⠋⠙⠹"

        txt.stop_animation = False
        while not txt.stop_animation:
            for char in chars:
                sys.stdout.write('\r' + prefix + ' ' + char + ' ')
                time.sleep(0.1)

    def stop_spinner_replace_text(text=None):
        if txt.activate_print == False:
            return None
        empty = 80 * ' '
        
        if not text:
            text = empty
            sys.stdout.write(f'\r{empty}')
        else:
            text = '✓ ' + text            
            sys.stdout.write(f'\r{empty}')
            sys.stdout.write(f'\r{text}\r\n')

        txt.stop_animation = True
        if txt.waiting_spinner_thread:
            txt.waiting_spinner_thread.join()
        
