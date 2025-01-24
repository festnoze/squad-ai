import asyncio
from typing import Union, Optional, get_origin, get_args
import inspect
import types
#
from common_tools.helpers.file_helper import file
from common_tools.helpers.method_decorator_helper import MethodDecorator
from common_tools.helpers.reflexion_helper import Reflexion
from common_tools.rag.rag_inference_pipeline.end_pipeline_exception import EndPipelineException

class WorkflowExecutor:
    def __init__(self, config_or_config_file_path=None, available_classes:dict={}):
        if isinstance(config_or_config_file_path, dict):
            self.config = config_or_config_file_path
        elif isinstance(config_or_config_file_path, str) and config_or_config_file_path:
            self.config = file.get_as_yaml(config_or_config_file_path)
        else:
            raise ValueError('config_or_config_file_path must be a dictionary or a file path to a YAML file.')
        
        self.available_classes = available_classes

    async def execute_workflow_async(self, workflow_config=None, previous_results=None, kwargs_values=None, config_entry_point_name=None):
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
            try:
                results = await self.execute_step_async(step, previous_results, kwargs_values, workflow_config)
                previous_results = results
            except EndPipelineException as epe:
                raise epe
        return results

    def _determine_workflow_config(self, config_entry_point_name):
        if config_entry_point_name:
            return self.config[config_entry_point_name]
        elif 'start' in self.config:
            return self.config['start']
        else:
            raise ValueError('Starting step must either be provided or a step named "start" must be set in config.')

    async def execute_step_async(self, step, previous_results, kwargs_values, workflow_config):
        if isinstance(step, dict):
            return await self.execute_dict_step_async(step, previous_results, kwargs_values)
        elif isinstance(step, list):
            return await self.execute_list_step_async(step, previous_results, kwargs_values)
        elif isinstance(step, str):
            return await self.execute_str_step_async(step, previous_results, kwargs_values, workflow_config)
        else:
            raise TypeError(f"Invalid step type: {type(step).__name__}")

    async def execute_dict_step_async(self, step, previous_results, kwargs_values):
        if 'parallel_async' in step:
            parallel_steps = step.get('parallel_async')
            parallel_results = await self.execute_parallel_steps_async(parallel_steps, previous_results, kwargs_values)
            return self.flatten_tuples(parallel_results)
        else:
            # Treat the dict as a sub-workflow
            sub_workflow_results = await self.execute_workflow_async(step, previous_results, kwargs_values)
            return self.flatten_tuples(sub_workflow_results)

    async def execute_list_step_async(self, step, previous_results, kwargs_values):
        sub_workflow_results = await self.execute_workflow_async(step, previous_results, kwargs_values)
        return self.flatten_tuples(sub_workflow_results)

    async def execute_str_step_async(self, step, previous_results, kwargs_values, workflow_config):
        if 'parallel_async' in step:
            if step in workflow_config:
                parallel_steps = workflow_config[step]
                parallel_results = await self.execute_parallel_steps_async(parallel_steps, previous_results, kwargs_values)
                return self.flatten_tuples(parallel_results)
            else:
                raise KeyError(f"Key '{step}' not found in the current workflow configuration.")
        elif step in self.config and isinstance(self.config[step], (list, dict)):
            sub_workflow_results = await self.execute_workflow_async(self.config[step], previous_results, kwargs_values)
            return self.flatten_tuples(sub_workflow_results)
        else:
            result = await self.execute_function_async(step, previous_results, kwargs_values)
            return [result]

    async def execute_parallel_steps_async(self, steps, previous_results, kwargs_values):
        tasks = [self.execute_func_or_workflow_async(step, previous_results, kwargs_values) for step in steps]
        return await asyncio.gather(*tasks)

    async def execute_func_or_workflow_async(self, step, previous_results, kwargs_values):
        if self._is_sub_workflow(step):
            inner_workflow_config = self.config[step]
            return await self.execute_workflow_async(inner_workflow_config, previous_results, kwargs_values)
        else:
            return await self.execute_function_async(step, previous_results, kwargs_values)

    def _is_sub_workflow(self, step):
        return isinstance(step, str) and step in self.config and isinstance(self.config[step], (list, dict))

    @MethodDecorator.print_func_execution_infos(display_param_value="class_and_function_name")
    def execute_function(self, class_and_function_name, previous_results, kwargs_values):
        func = Reflexion.get_static_method(class_and_function_name, self.available_classes)
        func_kwargs = self._prepare_arguments_for_function(func, previous_results, kwargs_values)
        
        try:
            if inspect.isgeneratorfunction(func):
                for item in func(**func_kwargs):
                    yield item
            else:
                result = func(**func_kwargs)
                self._add_function_output_names_and_values_to_kwargs(func, result, kwargs_values)
                yield result
        except EndPipelineException as epe:
            raise epe
        except Exception as e:
            self._raise_fail_func_execution(class_and_function_name, previous_results, kwargs_values, e)

    @MethodDecorator.print_func_execution_infos(display_param_value="class_and_function_name")
    async def execute_function_async(self, class_and_function_name, previous_results, kwargs_values):
        func = Reflexion.get_static_method(class_and_function_name, self.available_classes)
        func_kwargs = self._prepare_arguments_for_function(func, previous_results, kwargs_values)
        try:
            # if inspect.isasyncgenfunction(func):
            #     async for item in func(**func_kwargs):
            #         yield item
            # else:
            if inspect.iscoroutinefunction(func):
                result = await func(**func_kwargs)
            else:
                result = func(**func_kwargs)
            self._add_function_output_names_and_values_to_kwargs(func, result, kwargs_values)
            return result
        except EndPipelineException as epe:
            raise epe   
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
        previous_results_str = ', '.join(f'({type(result).__name__}) {str(result)[:25]}...' for result in previous_results)
        previous_results_str = previous_results_str[:100] + '... + size: ' + str(len(previous_results_str)) if len(previous_results_str) > 100 else previous_results_str
        
        error_message = (
                f"Error: {str(exception)}\n"
                f"Error occurred while executing class and function name: '{class_and_function_name}'\n"
                f"With previous results: {previous_results_str if previous_results else '<empty>'}\n"
                f"With kwargs values: {', '.join(list(kwargs_value.keys()))}.\n"
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
                continue

            if kwargs_value and arg_name in kwargs_value:
                func_kwargs[arg_name] = kwargs_value[arg_name]
                if prev_results_index < len(prev_results):
                    arg_value = prev_results[prev_results_index]
                    if isinstance(arg_value, list) and len(arg_value) == 1 and arg_value[0] == kwargs_value[arg_name]:
                        prev_results_index += 1
                    elif arg_value == kwargs_value[arg_name] and (
                            arg.annotation == inspect.Parameter.empty or
                            self._is_value_matching_annotation(arg_value, arg.annotation)):
                        prev_results_index += 1
            elif prev_results_index < len(prev_results):
                arg_value = prev_results[prev_results_index]
                if arg.annotation != inspect.Parameter.empty:
                    if not self._is_value_matching_annotation(arg_value, arg.annotation):
                        if arg.default is not inspect.Parameter.empty:
                            continue
                        else:
                            raise TypeError(
                                f"Type mismatch while preparing args for function: '{func.__name__}'. "
                                f"Provided value for argument '{arg_name}' is: '{type(arg_value).__name__}', "
                                f"but expected to be: '{arg.annotation}'")
                func_kwargs[arg_name] = arg_value
                prev_results_index += 1
            else:
                if arg.default is not inspect.Parameter.empty:
                    continue
                else:
                    raise TypeError(f"Missing argument: '{arg_name}', which is required, because it has no default value.")

        return func_kwargs

    def _is_value_matching_annotation(self, value, annotation):
        """
        Check if a value matches an annotation. Supports Optional, Union, and parameterized types like list[str].
        """
        origin = get_origin(annotation)  # Get the base type (e.g., list for list[str])
        args = get_args(annotation)  # Get the type arguments (e.g., [str] for list[str])

        if origin is Union:
            possible_types = args
            if type(None) in possible_types and value is None:
                return True
            return any(self._is_value_matching_annotation(value, t) for t in possible_types if t is not type(None))

        if origin in {list, set, tuple}:
            if not isinstance(value, origin):
                return False
            if args:
                # If type arguments are provided, check all elements
                return all(self._is_value_matching_annotation(item, args[0]) for item in value)
            return True  # If no type argument, just check it's a list/set/tuple

        if origin is dict:
            if not isinstance(value, dict):
                return False
            key_type, value_type = args if args else (None, None)
            return all(
                self._is_value_matching_annotation(k, key_type) and self._is_value_matching_annotation(v, value_type)
                for k, v in value.items()
            )

        if value is None and annotation == Optional:
            return True

        # Default check for non-parameterized types
        return isinstance(value, annotation)

    def _get_function_output_names(self, func):
        output_names = getattr(func, '_output_name', None)
        if output_names is not None:
            if isinstance(output_names, str):
                return {'output_names': [output_names]}
            elif isinstance(output_names, (list, tuple)):
                return {'output_names': list(output_names)}
        return None

    def flatten_tuples(self, items):
        """
        Flatten a list or tuple to make sure we pass a single-level list as *args.
        """
        flat_list = []
        for item in items:
            if isinstance(item, tuple):
                flat_list.extend(self.flatten_tuples(item))  # Recursively flatten if it's a nested iterable (tuple/set)
            else:
                flat_list.append(item)
        return flat_list
