import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib
import inspect
import typing
from collections.abc import Iterable
#
from common_tools.helpers.file_helper import file

class WorkflowExecutor:
    def __init__(self, config_or_config_file_path=None, available_classes:dict={}):
        if isinstance(config_or_config_file_path, dict):
            self.config = config_or_config_file_path
        elif isinstance(config_or_config_file_path, str) and config_or_config_file_path:
            self.config = file.get_as_yaml(config_or_config_file_path)
        else:
            raise ValueError('config_or_config_file_path must be a dictionary or a file path to a YAML file.')
        
        self.available_classes = available_classes

    def execute_workflow(self, workflow_config=None, previous_results:list=None, kwargs_values: dict = {}, config_entry_point_name: str = None):
        if not workflow_config:
            if config_entry_point_name:
                workflow_config = self.config[config_entry_point_name]
            elif 'start' in self.config:
                workflow_config = self.config['start']
            else:
                raise ValueError('Starting step must either be provided or a step named: "start" must be set in config.')
        else:
            if config_entry_point_name:
                workflow_config = workflow_config[config_entry_point_name]

        if not previous_results:
            previous_results = []
        if kwargs_values is None:
            kwargs_values = {}

        results = []
        for step in workflow_config:
            if isinstance(step, dict):
                if 'parallel_threads' in step:
                    parallel_steps = step['parallel_threads']
                    parallel_results = self.execute_steps_as_parallel_threads(parallel_steps, previous_results, kwargs_values)
                    results = self.flatten_tuples(parallel_results)
                elif 'parallel_async' in step:
                    parallel_steps = step['parallel_async']
                    parallel_results = asyncio.run(self.execute_steps_as_parallel_async(parallel_steps, previous_results, kwargs_values))
                    results = self.flatten_tuples(parallel_results)
                else:
                    for sub_workflow_name in step.keys():
                        sub_workflow_results = self.execute_workflow(self.config, previous_results, kwargs_values, sub_workflow_name)
                        results = self.flatten_tuples(sub_workflow_results)
            elif isinstance(step, list):
                sub_workflow_results = self.execute_workflow(step, previous_results, kwargs_values)
                results = self.flatten_tuples(sub_workflow_results)
            elif isinstance(step, str):
                if step == 'parallel_threads':
                    parallel_results = self.execute_steps_as_parallel_threads(workflow_config[step], previous_results, kwargs_values)
                    results = self.flatten_tuples(parallel_results)
                elif step == 'parallel_async':
                    parallel_results = asyncio.run(self.execute_steps_as_parallel_async(workflow_config[step], previous_results, kwargs_values))
                    results = self.flatten_tuples(parallel_results)
                elif step in self.config and isinstance(self.config[step], (list, dict)):
                    sub_workflow_results = self.execute_workflow(self.config, previous_results, kwargs_values, step)
                    results = self.flatten_tuples(sub_workflow_results)
                else:
                    result = self.execute_function(step, previous_results, kwargs_values)
                    results = [result]
                    # Update kwargs with any named outputs from the executed function
                    return_info = self._get_return_infos_for_function(self.get_static_method(step))
                    if return_info:
                        output_names = return_info['output_names']
                        if len(output_names) == 1:
                            kwargs_values[output_names[0]] = result
                        elif len(output_names) > 1 and isinstance(result, tuple):
                            for name, value in zip(output_names, result):
                                kwargs_values[name] = value
            else:
                pass
            previous_results = results
        return results

    def execute_steps_as_parallel_threads(self, steps, previous_results, kwargs_values):
        """
        Execute steps in parallel using ThreadPoolExecutor.
        """
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for step in steps:
                future = executor.submit(self.execute_func_or_workflow, step, previous_results, kwargs_values)
                futures.append(future)

            results = []
            for future in futures:
                result = future.result()
                results.append(result)

        return results

    async def execute_steps_as_parallel_async(self, steps, previous_results, kwargs_values):
        """
        Execute steps in parallel using asyncio coroutines.
        """
        tasks = [self.execute_async_func_or_workflow(step, previous_results, kwargs_values) for step in steps]
        results = await asyncio.gather(*tasks)
        return results

    def execute_func_or_workflow(self, step, previous_results, kwargs_values):
        """
        Helper method to decide whether to execute a step or a nested workflow.
        """
        if isinstance(step, str) and step in self.config and isinstance(self.config[step], (list, dict)):
            inner_workflow_config = self.config[step]
            return self.execute_workflow(inner_workflow_config, previous_results, kwargs_values)
        else:
            return self.execute_function(step, previous_results, kwargs_values)

    async def execute_async_func_or_workflow(self, step, previous_results, kwargs_values):
        """
        Async helper method to decide whether to execute a step or a nested workflow.
        """
        if isinstance(step, str) and step in self.config and isinstance(self.config[step], (list, dict)):
            inner_workflow_config = self.config[step]
            return await asyncio.to_thread(self.execute_workflow, inner_workflow_config, previous_results, kwargs_values)
        else:
            return await self.execute_function_async(step, previous_results, kwargs_values)


    async def execute_function_async(self, class_and_function_name, previous_results, kwargs_value):
        func = self.get_static_method(class_and_function_name)
        func_kwargs = self._prepare_arguments_for_function(func, previous_results, kwargs_value)
        try:
            if inspect.iscoroutinefunction(func):
                result = await func(**func_kwargs)
            else:
                result = func(**func_kwargs)
            return result        
        except Exception as e:
            self._raise_fail_func_exection(class_and_function_name, previous_results, kwargs_value, e)

    def execute_function(self, class_and_function_name: str, previous_results: list, kwargs_value: dict):
        func = self.get_static_method(class_and_function_name)       
        func_kwargs = self._prepare_arguments_for_function(func, previous_results, kwargs_value)
        try:
            result = func(**func_kwargs)
            return_info = self._get_return_infos_for_function(func)
            if return_info:
                output_names = return_info['output_names']
                if len(output_names) == 1:
                    kwargs_value[output_names[0]] = result
                elif len(output_names) > 1 and isinstance(result, tuple):
                    for name, value in zip(output_names, result):
                        kwargs_value[name] = value
            return result            
        except Exception as e:
            self._raise_fail_func_exection(class_and_function_name, previous_results, kwargs_value, e)        
    
    def _raise_fail_func_exection(self, class_and_function_name, previous_results, kwargs_value, e):
        error_message = (
                f"Error occurred while executing function: {str(e)}\n"
                f"Class and function name: {class_and_function_name}\n"
                f"Previous results: {previous_results}\n"
                f"Kwargs values: {kwargs_value}"
            )
        raise RuntimeError(error_message) from e

    def _prepare_arguments_for_function(self, func, previous_results: list, kwargs_value: dict):
        """
        Prepares keyword arguments for a function call.

        Arguments are filled from kwargs_value first (matching by parameter names),
        and then from previous_results if not already in kwargs_value. Each argument
        from previous_results is used only once and removed from the list. If there
        are not enough arguments to satisfy the function's required parameters,
        raises an error.

        If the type of a value from previous_results does not match the expected
        type of the function parameter, raises a TypeError.
        """
        func_kwargs = {}
        sig = inspect.signature(func)
        function_args = sig.parameters.items()
        prev_results = previous_results if previous_results is not None else []
        prev_results_index = 0

        for arg_name, arg in function_args:
            if arg.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                # Skip *args and **kwargs handling
                continue

            if kwargs_value and arg_name in kwargs_value:
                # Use the value from kwargs_value
                func_kwargs[arg_name] = kwargs_value[arg_name]
                # Check if it also matches the next value from previous_results
                if prev_results_index < len(prev_results):
                    arg_value = prev_results[prev_results_index]
                    if isinstance(arg_value, list) and len(arg_value) == 1 and arg_value[0] == kwargs_value[arg_name]:
                        prev_results_index += 1
                    elif arg_value == kwargs_value[arg_name] and (arg.annotation == inspect.Parameter.empty or isinstance(arg_value, arg.annotation)):
                        prev_results_index += 1
            elif prev_results_index < len(prev_results):
                # Use the next value from previous_results if not already set in kwargs
                arg_value = prev_results[prev_results_index]
                # Raise an error only if: The arg type is specified, the previous_results value type does not match it, and the arg has no default value
                if arg.annotation != inspect.Parameter.empty and not WorkflowExecutor.is_matching_type_and_subtypes(arg_value, arg.annotation):
                    if arg.default is not inspect.Parameter.empty:
                        continue
                    else:
                        raise TypeError(f"Type mismatch for argument '{arg_name}': expected {arg.annotation}, got {type(arg_value)}")
                func_kwargs[arg_name] = arg_value
                prev_results_index += 1
            else:
                if arg.default is not inspect.Parameter.empty:
                    continue
                else:
                    raise TypeError(f"Missing argument: '{arg_name}', which is required, because it has no default value.")

        return func_kwargs

    def _get_return_infos_for_function(self, func):
        output_names = getattr(func, '_output_name', None)
        if output_names is not None:
            if isinstance(output_names, str):
                return {'output_names': [output_names]}
            elif isinstance(output_names, (list, tuple)):
                return {'output_names': list(output_names)}
        return None
    
    @staticmethod
    def is_matching_type_and_subtypes(arg_value, param_annotation):
        # If value has no type (=None), or the receiving parameter has no defined type, it's a match
        if arg_value is None or param_annotation is inspect.Parameter.empty:
            return True
        
        origin, args = typing.get_origin(param_annotation), typing.get_args(param_annotation)

        if origin in {list, tuple, set}:
            if not isinstance(arg_value, origin):
                return False
            if not args:
                return True
            if origin in {list, set}:
                return all(WorkflowExecutor.is_matching_type_and_subtypes(item, args[0]) for item in arg_value)
            elif origin is tuple:
                return all(WorkflowExecutor.is_matching_type_and_subtypes(item, args[i]) for i, item in enumerate(arg_value))
            else:
                raise ValueError(f"Unhandled origin type: {origin}")
        
        if origin is dict:
            return isinstance(arg_value, dict) and (not args or all(
                WorkflowExecutor.is_matching_type_and_subtypes(k, args[0]) and 
                WorkflowExecutor.is_matching_type_and_subtypes(v, args[1])
                for k, v in arg_value.items()
            ))

        return isinstance(arg_value, origin or param_annotation)

    def get_function_by_name_dynamic(self, step_name):
        """
        Given a string like 'RAGPreTreatment.analyse_query_language', return the function.
        """
        module_name, func_name = step_name.rsplit('.', 1)
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        return func
    
    def get_static_method(self, class_and_function_name):
        """
        Retrieve a function or class method based on a string name.
        
        The format should be 'Class.method', where Class is one of the pre-imported classes.
        """
        parts = class_and_function_name.split('.')
        if len(parts) != 2: raise ValueError(f"Invalid function name '{class_and_function_name}'. It should be in 'Class.method' format.")
        class_name, method_name = parts
        
        cls = self.available_classes.get(class_name)
        if not cls:
            raise ValueError(f"Class '{class_name}' not found.")
        
        # Check if the method exists in the class
        method = getattr(cls, method_name, None)
        if method is None or not callable(method):
            raise AttributeError(f"Class '{class_name}' does not have a callable method '{method_name}'.")
        
        return method
    
    def get_function(self, class_and_function_name, instance=None):
        """
        Retrieve a function or class method based on a string name.

        The format should be 'Class.method', where Class is one of the pre-imported classes.
        If an instance of the class is provided, the method will be bound to that instance.
        If no instance is provided, and the method is not static, the class will be instantiated.
        """
        parts = class_and_function_name.split('.')
        if len(parts) != 2:
            raise ValueError(f"Invalid function name '{class_and_function_name}'. It should be in 'Class.method' format.")
        
        class_name, method_name = parts

        # Retrieve the class from the available_classes
        cls = self.available_classes.get(class_name)
        if not cls:
            raise ValueError(f"Class '{class_name}' not found.")

        # Check if the method exists in the class
        method = getattr(cls, method_name, None)
        if method is None or not callable(method):
            raise AttributeError(f"Class '{class_name}' does not have a callable method '{method_name}'.")

        # If an instance is provided, bind the method to the instance
        if instance:
            return getattr(instance, method_name)
        
        # If no instance is provided and the method is not static, create an instance of the class
        if not isinstance(method, staticmethod):
            # Instantiate the class if no instance is provided
            instance = cls()
            return getattr(instance, method_name)

        # For static methods, simply return the method
        return method

    def get_function_kwargs_with_values(self, func, provided_kwargs):
        """
        Inspects a function and returns a dictionary of the required arguments
        filtered from the available kwargs. Raises KeyError if a required 
        argument without a default value is missing.
        """
        sig = inspect.signature(func)
        required_args = {}
        for param_name, param in sig.parameters.items():
            if param.default == inspect.Parameter.empty and param_name not in provided_kwargs:
                raise KeyError(f"Missing required argument: {param_name}")
            if param_name in provided_kwargs:
                required_args[param_name] = provided_kwargs[param_name]

        return required_args

    def flatten_tuples(self, items):
        """
        Flatten a list or tuple to make sure we pass a single-level list as *args.
        """
        flat_list = []
        for item in items:
            if isinstance(item, Iterable) and not isinstance(item, (str, bytes, dict, list)):
                flat_list.extend(self.flatten_tuples(item))  # Recursively flatten if it's a nested iterable (tuple/set)
            else:
                flat_list.append(item)
        return flat_list
