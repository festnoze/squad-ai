from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import inspect
import threading
from types import FunctionType

from common_tools.helpers.txt_helper import txt

class Execute:
    @staticmethod
    def run_parallel(*functions_with_args):
        """
        Run the provided functions in parallel and return their results as a tuple.
        Supports function calls in multiple formats:
        - `task_a` : A function with no arguments
        - `(task_b, ("John",))` : Function with positional arguments
        - `(task_c, (2, 3), {'c': 5})` : Function with positional and keyword arguments
        :param functions_with_args: Functions with optional args/kwargs
        :return: Tuple of results in the same order as the provided functions
        """

        # Dynamically set max_workers based on the number of functions
        num_functions = len(functions_with_args)
        if num_functions == 0: 
            return ()
        
        results = [None] * num_functions
        
        # Use ThreadPoolExecutor to execute the functions in parallel
        with ThreadPoolExecutor(max_workers=num_functions) as executor:
            futures = []

            for index, item in enumerate(functions_with_args):
                # If the item is a function without arguments
                if callable(item):
                    futures.append((executor.submit(item), index))

                # If the item is a tuple with a function and its arguments
                elif isinstance(item, tuple):
                    func = item[0]
                    args = item[1] if len(item) > 1 else ()
                    kwargs = item[2] if len(item) > 2 else {}

                    # Ensure args is a tuple, even if it's a single non-iterable object (e.g., QuestionAnalysis)
                    if not isinstance(args, tuple):
                        args = (args,)

                    # Check if args contain non-iterable objects and wrap them in a tuple
                    if not isinstance(args, (tuple, list)):
                        args = (args,)

                    futures.append((executor.submit(func, *args, **kwargs), index))

                else:
                    raise ValueError(f"Invalid input: {item}")

            # Collect results based on the original order of submission
            for future, index in futures:
                results[index] = future.result()

        return tuple(results)
    
    @staticmethod
    def activate_global_function_parameters_types_verification():
        sys.setprofile(Execute._activate_strong_typed_functions_parameters)
        #threading.setprofile(Execute._activate_strong_typed_functions_parameters)

    @staticmethod
    def deactivate_global_function_parameters_types_verification():
        sys.setprofile(None)
        #threading.setprofile(None)

    @staticmethod
    def _activate_strong_typed_functions_parameters(frame, event, arg):
        """todo: don't work for now, work further or use decorator instead"""
        # We are only interested in function calls, not returns or other events
        if event != "call":
            return

        # Get the function being called using the code object in the frame
        func = frame.f_globals.get(frame.f_code.co_name)
        if not func:
            txt.print(f"Function not found: '{frame.f_code.co_name}'")
            return
        
        txt.print(f"Get function: '{func.__name__}")
        # Check if the object is a function
        if not isinstance(func, FunctionType):
            return

        try:
            # Get the function signature using the inspect module
            signature = inspect.signature(func)
            txt.print(f"Get function signature: '{func.__name__}")

            # The arguments passed to the function are stored in frame.f_locals
            args = frame.f_locals
            txt.print(f"Get arguments passed to the function: '{func.__name__}")
            for name, param in signature.parameters.items():
                # Check if the current argument has been passed and if it has an expected type annotation
                if name in args:
                    expected_type = param.annotation
                    if expected_type is not inspect.Parameter.empty:
                        txt.print(f"Get not empty argument: '{name} passed to the function: '{func.__name__}")
                        value = args[name]
                        if not value:
                            txt.print(f"No value found for argument: '{name} passed to the function: '{func.__name__}")
                            continue
                        # Verify if the value's type matches the expected arg's type
                        if not isinstance(value, expected_type):
                            txt.print(f"Get value: '{value}' for argument: '{name} passed to the function: '{func.__name__}  which does't match the expected type: '{expected_type.__name__}")
                            raise TypeError(f"Argument '{name}' of function '{func.__name__}' must be of type {expected_type.__name__}, but got {type(value).__name__}")

        except ValueError as e:
            txt.print(e)
        except TypeError as e:
            txt.print(e)

