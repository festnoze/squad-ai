import sys
import threading
import time
from helpers.python_helpers import staticproperty
from threading import Event, Thread

class txt:    
    waiting_spinner_thread = None
    start_time: float = None
    stop_event = Event()
    
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
        
    def get_elapsed_seconds(start_time, end_time):
        if not start_time or not end_time:
            return 0
        return int(end_time - start_time)
        
    
    def get_elapsed_str(elapsed_sec: int):
        elapsed_str = ''
        elapsed_minutes = int(elapsed_sec / 60)
        elapsed_seconds = int(elapsed_sec % 60)

        if elapsed_minutes != 0:
            elapsed_str += f"{elapsed_minutes}m "
        elapsed_str +=  f"{elapsed_seconds}s"
        return '(' + elapsed_str + ')'
    
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

    def print_with_spinner(text: str) -> Thread:
        if not txt.activate_print:
            return None
        txt.start_time = time.time()

        # Ensure only one spinner thread is running at a time
        if txt.waiting_spinner_thread and txt.waiting_spinner_thread.is_alive():
            raise Exception("Previous waiting spinner thread wasn't halted before creating a new one")

        txt.stop_event.clear()
        txt.waiting_spinner_thread = Thread(target=txt.wait_spinner, args=(text,))
        txt.waiting_spinner_thread.daemon = True
        txt.waiting_spinner_thread.start()
        return txt.waiting_spinner_thread
    
    def to_python_case(text: str) -> str:
        return ''.join(['_' + c.lower() if c.isupper() else c for c in text]).lstrip('_')

    def wait_spinner(prefix):
        chars = "⠸⠼⠴⠦⠧⠇⠏⠋⠙⠹"
        while not txt.stop_event.is_set():
            for char in chars:
                if txt.stop_event.is_set():
                    break
                sys.stdout.write('\r' + prefix + ' ' + char + ' ')
                sys.stdout.flush()
                time.sleep(0.1)

    def stop_spinner():
        txt.stop_event.set()  # Signal the thread to stop
        if txt.waiting_spinner_thread:
            txt.waiting_spinner_thread.join()
            txt.waiting_spinner_thread = None

    def stop_spinner_replace_text(text=None)-> int:
        txt.stop_spinner()
        if not txt.activate_print:
            return None
        
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
                    elapsed_str = f" {elapsed_str}."
                else:
                    elapsed_str = ''         
                txt.start_time = None

            text = f"✓ {text}{elapsed_str}" 
            sys.stdout.write(f'\r{empty}')
            sys.stdout.write(f'\r{text}\r\n')
            return elapsed_sec if elapsed_sec else 0