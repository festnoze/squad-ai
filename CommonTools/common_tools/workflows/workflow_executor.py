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

    def execute_workflow(self, workflow_config=None, previous_results=None, kwargs_values=None, config_entry_point_name=None):
        if workflow_config is None:
            workflow_config = self._determine_workflow_config(config_entry_point_name)
        else:
            if config_entry_point_name:
                workflow_config = workflow_config[config_entry_point_name]
        if previous_results is None:
            previous_results = []
        if kwargs_values is None:
            kwargs_values = {}
        
        results = []
        for step in workflow_config:
            results = self.execute_step(step, previous_results, kwargs_values, workflow_config)
            previous_results = results
        return results

    def _determine_workflow_config(self, config_entry_point_name):
        if config_entry_point_name:
            return self.config[config_entry_point_name]
        elif 'start' in self.config:
            return self.config['start']
        else:
            raise ValueError('Starting step must either be provided or a step named "start" must be set in config.')

    def execute_step(self, step, previous_results, kwargs_values, workflow_config):
        if isinstance(step, dict):
            return self.execute_dict_step(step, previous_results, kwargs_values)
        elif isinstance(step, list):
            return self.execute_list_step(step, previous_results, kwargs_values)
        elif isinstance(step, str):
            return self.execute_str_step(step, previous_results, kwargs_values, workflow_config)
        else:
            raise TypeError(f"Invalid step type: {type(step).__name__}")

    def execute_dict_step(self, step, previous_results, kwargs_values):
        if 'parallel_threads' in step or 'parallel_async' in step:
            parallel_type = 'threads' if 'parallel_threads' in step else 'async'
            parallel_steps = step.get('parallel_threads') or step.get('parallel_async')
            parallel_results = self.execute_parallel_steps(parallel_steps, previous_results, kwargs_values, parallel_type)
            return self.flatten_tuples(parallel_results)
        else:
            # Treat the dict as a sub-workflow
            sub_workflow_results = self.execute_workflow(step, previous_results, kwargs_values)
            return self.flatten_tuples(sub_workflow_results)

    def execute_list_step(self, step, previous_results, kwargs_values):
        sub_workflow_results = self.execute_workflow(step, previous_results, kwargs_values)
        return self.flatten_tuples(sub_workflow_results)

    def execute_str_step(self, step, previous_results, kwargs_values, workflow_config):
        if step in ['parallel_threads', 'parallel_async']:
            parallel_type = 'threads' if step == 'parallel_threads' else 'async'
            if step in workflow_config:
                parallel_steps = workflow_config[step]
                parallel_results = self.execute_parallel_steps(parallel_steps, previous_results, kwargs_values, parallel_type)
                return self.flatten_tuples(parallel_results)
            else:
                raise KeyError(f"Key '{step}' not found in the current workflow configuration.")
        elif step in self.config and isinstance(self.config[step], (list, dict)):
            sub_workflow_results = self.execute_workflow(self.config[step], previous_results, kwargs_values)
            return self.flatten_tuples(sub_workflow_results)
        else:
            result = self.execute_function(step, previous_results, kwargs_values)
            return [result]

    def execute_parallel_steps(self, steps, previous_results, kwargs_values, parallel_type):
        if parallel_type == 'threads':
            return self._execute_steps_in_threads(steps, previous_results, kwargs_values)
        elif parallel_type == 'async':
            return asyncio.run(self._execute_steps_in_async(steps, previous_results, kwargs_values))
        else:
            raise ValueError(f"Unknown parallel execution type: {parallel_type}")

    def _execute_steps_in_threads(self, steps, previous_results, kwargs_values):
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(self.execute_func_or_workflow, step, previous_results, kwargs_values) for step in steps]
            return [future.result() for future in futures]

    async def _execute_steps_in_async(self, steps, previous_results, kwargs_values):
        tasks = [self.execute_async_func_or_workflow(step, previous_results, kwargs_values) for step in steps]
        return await asyncio.gather(*tasks)

    def execute_func_or_workflow(self, step, previous_results, kwargs_values):
        if self._is_sub_workflow(step):
            inner_workflow_config = self.config[step]
            return self.execute_workflow(inner_workflow_config, previous_results, kwargs_values)
        else:
            return self.execute_function(step, previous_results, kwargs_values)

    async def execute_async_func_or_workflow(self, step, previous_results, kwargs_values):
        if self._is_sub_workflow(step):
            inner_workflow_config = self.config[step]
            return await asyncio.to_thread(self.execute_workflow, inner_workflow_config, previous_results, kwargs_values)
        else:
            return await self.execute_function_async(step, previous_results, kwargs_values)

    def _is_sub_workflow(self, step):
        return isinstance(step, str) and step in self.config and isinstance(self.config[step], (list, dict))

    def execute_function(self, class_and_function_name, previous_results, kwargs_values):
        func = self.get_static_method(class_and_function_name)
        func_kwargs = self._prepare_arguments_for_function(func, previous_results, kwargs_values)
        
        try:
            result = func(**func_kwargs)
        except Exception as e:
            self._raise_fail_func_execution(class_and_function_name, previous_results, kwargs_values, e)

        self._add_function_output_names_and_values_to_kwargs(func, result, kwargs_values)
        return result

    async def execute_function_async(self, class_and_function_name, previous_results, kwargs_values):
        func = self.get_static_method(class_and_function_name)
        func_kwargs = self._prepare_arguments_for_function(func, previous_results, kwargs_values)
        try:
            if inspect.iscoroutinefunction(func):
                result = await func(**func_kwargs)
            else:
                result = func(**func_kwargs)
            self._add_function_output_names_and_values_to_kwargs(func, result, kwargs_values)
            return result
        except Exception as e:
            self._raise_fail_func_execution(class_and_function_name, previous_results, kwargs_values, e)

    def _add_function_output_names_and_values_to_kwargs(self, func, function_results, kwargs_values):
        return_info = self._get_function_output_names(func)
        if return_info:
            output_names = return_info['output_names']
            output_names_count = len(output_names)
            
            if output_names_count == 0:
                return
            elif output_names_count == 1:
                kwargs_values[output_names[0]] = function_results
            elif output_names_count > 1:
                if not isinstance(function_results, tuple) or output_names_count > len(function_results):
                    raise ValueError(f"Function only returned {len(function_results) if isinstance(function_results, tuple) else 1} values, but at least {output_names_count} were expected to match with output names decorator.")
                for name, value in zip(output_names, function_results[:output_names_count]):
                    kwargs_values[name] = value 
    
    def _raise_fail_func_execution(self, class_and_function_name, previous_results:list, kwargs_value, exception):
        previous_results_str = ', '.join(str(result) for result in previous_results)
        previous_results_str = previous_results_str[:100] + '... + size: ' + str(len(previous_results_str)) if len(previous_results_str) > 100 else previous_results_str
        
        error_message = (
                f"Error: {str(exception)}\n"
                f"Error occurred while executing class and function name: '{class_and_function_name}'\n"
                f"With previous results: {previous_results_str}\n"
                f"With kwargs values: {kwargs_value}.\n"
            )
        raise RuntimeError(error_message) from exception

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
                        raise TypeError(f"Type mismatch while preparing args for function: '{func.__name__}'. Provided value for argument '{arg_name}' is: '{type(arg_value).__name__}', but expected to be: '{arg.annotation.__name__}'")

                func_kwargs[arg_name] = arg_value
                prev_results_index += 1
            else:
                if arg.default is not inspect.Parameter.empty:
                    continue
                else:
                    raise TypeError(f"Missing argument: '{arg_name}', which is required, because it has no default value.")

        return func_kwargs

    def _get_function_output_names(self, func):
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
        if len(parts) != 2: 
            raise ValueError(f"Invalid function name '{class_and_function_name}'. It should be in 'Class.method' format.")
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
