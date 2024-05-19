import sys
import threading
import time
from helpers.python_helpers import staticproperty
from threading import Event, Thread

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
        
    def get_elapsed_str(start_time, end_time):
        if not start_time or not end_time:
            return None
        elapsed_sec = int(end_time - start_time)
        elapsed_minutes = int(elapsed_sec / 60)
        elapsed_seconds = int(elapsed_sec % 60)

        if elapsed_sec == 0:
            return None
        
        elapsed_str = ''
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

    def __init__(self):
        self.waiting_spinner_thread = None
        self.start_time: float = None
        self.stop_event = Event()
        print("\rinit txt - " + str(self.stop_animation))

    def print_with_spinner(self, text: str) -> Thread:
        if not txt.activate_print:
            return None
        txt.start_time = time.time()

        # Ensure only one spinner thread is running at a time
        if self.waiting_spinner_thread and self.waiting_spinner_thread.is_alive():
            raise Exception("Previous waiting spinner thread wasn't halt before creating a new one")

        self.waiting_spinner_thread = Thread(target=self.wait_spinner, args=(text,))
        self.waiting_spinner_thread.daemon = True
        self.waiting_spinner_thread.start()
        return self.waiting_spinner_thread


    def wait_spinner(self, prefix):  # Optional prefix text
        # Spinner characters
        chars = "⠸⠼⠴⠦⠧⠇⠏⠋⠙⠹"

        self.stop_animation = False
        print("\rwaiting_spinner_thread started - " + str(self.stop_animation))
        while not self.stop_animation:
            for char in chars:
                if self.stop_animation:
                    break
                sys.stdout.write('\r' + prefix + ' ' + char + ' ')
                sys.stdout.flush()
                time.sleep(0.1)


    def stop_spinner(self):
        self.stop_animation = True
        print("\rwaiting_spinner_thread stopped - " + str(self.stop_animation))
        if self.waiting_spinner_thread:
            self.stop_animation = True
            self.waiting_spinner_thread.join()
            self.waiting_spinner_thread = None


    def stop_spinner_replace_text(self, text=None):
        self.stop_spinner()
        if not txt.activate_print:
            return None
        
        empty = 120 * ' '
        if not text:
            text = empty
            sys.stdout.write(f'\r{empty}')
        else:
            elapsed_str = ''
            if txt.start_time:
                elapsed_str = txt.get_elapsed_str(self.start_time, time.time())
                if elapsed_str:
                    elapsed_str = f" {elapsed_str}."             
                txt.start_time = None

            text = f"✓ {text}{elapsed_str}" 
            sys.stdout.write(f'\r{empty}')
            sys.stdout.write(f'\r{text}\r\n')