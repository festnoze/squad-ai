from concurrent.futures import ThreadPoolExecutor, as_completed

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
        if num_functions == 0: return ()
        
        results = [None] * len(functions_with_args) 
        
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

                    # Ensure args is a tuple, even if it's a single string
                    if isinstance(args, str):
                        args = (args,)

                    futures.append((executor.submit(func, *args, **kwargs), index))

                else:
                    raise ValueError(f"Invalid input: {item}")

            # Collect results based on the original order of submission
            for future, index in futures:
                results[index] = future.result()

        return tuple(results)