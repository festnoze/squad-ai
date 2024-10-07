import asyncio
import uuid
import pytest
from langchain_core.documents import Document
from common_tools.workflows.output_name_decorator import output_name
from common_tools.workflows.workflow_executor import WorkflowExecutor

class Test_WorkflowExecutor:

    def setup_method(self, method):
        self.config = {}
        self.executor = WorkflowExecutor(config_or_config_file_path=self.config, available_classes={'workflow_executor_test_methods': workflow_executor_test_methods})

    def teardown_method(self, method):
        self.config = None
        self.executor = None


    def test_get_required_args(self):
        def func(a, b, c=3):
            pass
        provided_kwargs = {'a': 1, 'b': 2, 'd': 4}
        expected = {'a': 1, 'b': 2}
        assert self.executor.get_function_kwargs_with_values(func, provided_kwargs) == expected

    @pytest.mark.parametrize("nested_list, expected", [
        ([1, (2, (3, 4)), 5, {6, 7}], [1, 2, 3, 4, 5, 6, 7]), # Basic nested list with tuples and sets, including different levels of nesting
        ([1, {2, 3}, (4, 5)], [1, 2, 3, 4, 5]), # Set containing nested tuples
        ([None, (1, 2)], [None, 1, 2]), # Mix of None and nested tuples
        ([1, (2, 3), {4, 5}], [1, 2, 3, 4, 5]), # Nested tuples and sets
        (['a', ('b', ('c', 'd'))], ['a', 'b', 'c', 'd']), # Strings should remain intact
        ([1, (2, {"key": "value"})], [1, 2, {"key": "value"}]), # Dictionary within list - dicts shouldn't be flattened
        ([1, ('a', {True, 3.14}), 8], [1, 'a', True, 3.14, 8]), # Mixed data types with tuples and sets
        ([1, 2, 3, 4], [1, 2, 3, 4]), # Completely flat list - should return as is
        ([1, (2, (3, {4, 5})), 6], [1, 2, 3, 4, 5, 6]), # Deeply nested with tuples and sets
        ([1, ((), set(), (2, 3)), {}, []], [1, 2, 3, {}, []]), # Empty sets or tuples removed, not empty list or dict
        ([1, ['a', [True, [3.14, None]]], {'key': 'value'}], [1, ['a', [True, [3.14, None]]], {'key': 'value'}]), # Nested lists of lists
        ([1, (2, {'a': 10, 'b': 20}), 3], [1, 2, {'a': 10, 'b': 20}, 3]), # List containing dictionary - dicts shouldn't be flattened
    ])
    def test_flatten(self, nested_list, expected):
        result = self.executor.flatten_tuples(nested_list)
        assert result == expected

    def test_prepare_arguments_simple_case(self):
        func = workflow_executor_test_methods.sample_function
        previous_results = [42, "test", 3.14]
        kwargs_value = {}

        kwargs = self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)
        assert kwargs == {'arg1': 42, 'arg2': 'test', 'arg3': 3.14}

    def test_prepare_arguments_mixed_case(self):
        func = workflow_executor_test_methods.sample_function
        previous_results = ["test", 3.14]  # 3.14 should not be used due to type mismatch with arg4 (bool)
        kwargs_value = {'arg1': 42, 'arg3': 2.71}

        kwargs = self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)
        assert kwargs == {'arg1': 42, 'arg2': 'test', 'arg3': 2.71}

    def test_prepare_arguments_complex_case(self):
        func = workflow_executor_test_methods.sample_function
        previous_results = ["from_previous_results", 123]  # 123 is an int, type mismatch for arg4 (bool)
        kwargs_value = {'arg1': 1, 'arg3': 3.14}

        kwargs = self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)
        assert kwargs == {'arg1': 1, 'arg2': 'from_previous_results', 'arg3': 3.14}

    def test_missing_required_argument(self):
        func = workflow_executor_test_methods.sample_function
        previous_results = []
        kwargs_value = {}

        with pytest.raises(TypeError, match="Missing required argument: arg1"):
            self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)

    def test_prepare_arguments_with_defaults(self):
        func = workflow_executor_test_methods.another_function
        previous_results = [5]
        kwargs_value = {}

        kwargs = self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)
        assert kwargs == {'arg1': 5}

    def test_prepare_arguments_varargs_case(self):
        func = workflow_executor_test_methods.varargs_function
        previous_results = [10, "extra", 2.5]
        kwargs_value = {}

        kwargs = self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)
        assert kwargs == {'arg1': 10, 'arg2': 'extra', 'arg3': 2.5}
        assert not any(previous_results)

    def test_kwarg_override(self):
        func = workflow_executor_test_methods.sample_function
        previous_results = [42, "test"]
        kwargs_value = {'arg3': 6.28, 'arg4': False}

        kwargs = self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)
        assert kwargs == {'arg1': 42, 'arg2': 'test', 'arg3': 6.28, 'arg4': False}

    def test_execute_from_kwargs(self):
        kwargs_values = {'a': 1, 'b': 2}
        result = self.executor.execute_function('workflow_executor_test_methods.step_one', [], kwargs_values)
        assert result == 3

    def test_execute_from_kwargs_and_previous_results(self):
        kwargs_values = {'a': 1}
        previous_results = [51]
        result = self.executor.execute_function('workflow_executor_test_methods.step_one', previous_results, kwargs_values)
        assert result == 52

    def test_execute_step_subsequent_step(self):
        previous_results = [3]
        result = self.executor.execute_function('workflow_executor_test_methods.step_two', previous_results, {})
        assert result == 6

    def test_execute_workflow_single_step(self):    
        steps_config = ['workflow_executor_test_methods.step_one']
        kwargs = {'a': 2, 'b': 3}
        results = self.executor.execute_workflow(steps_config, kwargs_values=kwargs)
        assert results == [5]

    def test_execute_workflow_sequential_steps(self):
        steps_config = [
            'workflow_executor_test_methods.step_one', 
            'workflow_executor_test_methods.step_two', 
            'workflow_executor_test_methods.step_three'
        ]
        kwargs = {'a': 2, 'b': 3}
        results = self.executor.execute_workflow(steps_config, kwargs_values=kwargs)
        assert results == [9]

    def test_execute_workflow_parallel_threads(self):
        steps_config = [
            {
                'parallel_threads': 
                [
                    'workflow_executor_test_methods.step_one', 
                    'workflow_executor_test_methods.step_three'
                ]
            }
        ]
        kwargs = {'a': 2, 'b': 3, 'd': 5}
        results = self.executor.execute_workflow(steps_config, kwargs_values=kwargs)
        assert results == [5, 4]

    def test_execute_workflow_parallel_async(self):
        steps_config = [{'parallel_async': ['workflow_executor_test_methods.step_async', 'workflow_executor_test_methods.step_three']}]
        kwargs = {'e': 3, 'd': 10}
        results = self.executor.execute_workflow(steps_config, kwargs_values=kwargs)
        assert results == [9, 9]

    def test_execute_workflow_nested_steps(self):
        self.executor.config = {
            'nested_steps': ['workflow_executor_test_methods.step_two', 'workflow_executor_test_methods.step_three']
        }
        steps_config = ['workflow_executor_test_methods.step_one', 'nested_steps']
        kwargs = {'a': 2, 'b': 3}
        results = self.executor.execute_workflow(steps_config, kwargs_values=kwargs)
        assert results == [9]

    def test_execute_parallel_threads(self):
        self.executor.config = {
            'start': {
                'parallel_threads': [
                    'workflow_executor_test_methods.step_one', 
                    'workflow_executor_test_methods.step_three'
                ]
            }
        }
        kwargs = {'a': 2, 'b': 3, 'd': 5}
        results = self.executor.execute_workflow(**kwargs)
        assert results == [5, 4]

    def test_execute_parallel_async(self):
        self.executor.config = {
            'start': {
                'parallel_async': [
                    'workflow_executor_test_methods.step_async', 
                    'workflow_executor_test_methods.step_three'
                ]
            }
        }
        kwargs = {'d': 5, 'e': 4}
        results = self.executor.execute_workflow(**kwargs)
        assert results == [16, 4]

    def test_execute_parallel_async_sub_workflow(self):
        self_config = {
            'sub1': {
                'parallel_async': [
                    'workflow_executor_test_methods.step_async', 
                    'workflow_executor_test_methods.step_three'
                ]
            }
        }
        kwargs = {'d': 5, 'e': 4}
        results = self.executor.execute_workflow(self_config, kwargs_values=kwargs, config_entry_point_name='sub1')
        assert results == [16, 4]

    def test_execute_step_missing_args(self):
        with pytest.raises(TypeError):
            self.executor.execute_function('workflow_executor_test_methods.step_one', [], **{})

    def test_execute_workflow_missing_function(self):
        steps_config = ['unknown_step']
        with pytest.raises(ValueError):
            self.executor.execute_workflow(steps_config, **{})

    def test_execute_workflow_with_tuple_output(self):
        def step_returns_tuple():
            return (1, 2)
        self.executor.get_static_method = lambda name: step_returns_tuple
        result = self.executor.execute_function('any_step', [], {})
        assert result == (1, 2)

    def test_get_function_by_name(self):
        func = self.executor.get_function('workflow_executor_test_methods.step_one')
        assert func.__name__ == workflow_executor_test_methods.step_one.__name__

    def test_execute_workflow_full(self):
        self.executor.config = {
            'sub_workflow': [
                {
                    'parallel_threads': 
                    [
                        'workflow_executor_test_methods.step_two', 
                        'workflow_executor_test_methods.step_three'
                    ]
                }
            ]
        }
        steps_config = ['workflow_executor_test_methods.step_one', 'sub_workflow']
        kwargs = {'a': 2, 'b': 3, 'c': 4, 'd': 6}
        results = self.executor.execute_workflow(steps_config, kwargs_values=kwargs)
        assert results == [8, 5]

    def test_invalid_workflow_config(self):
        steps_config = 123  # Non-iterable
        with pytest.raises(TypeError):
            self.executor.execute_workflow(steps_config)

    def test_execute_workflow_no_kwargs(self):
        steps_config = ['workflow_executor_test_methods.step_four']
        result = self.executor.execute_workflow(steps_config)
        assert result == [7]

    def test_execute_function_using_previous_results(self):  
        previous_results = [1, 2]
        result = self.executor.execute_function('workflow_executor_test_methods.step_one', previous_results, {})
        assert result == 3 

    def test_parallel_threads_with_empty_steps(self):
        results = self.executor.execute_steps_as_parallel_threads([], [], {})
        assert results == []  # No steps to execute

    @pytest.mark.asyncio
    async def test_parallel_async_with_empty_steps(self):
        results = await self.executor.execute_steps_as_parallel_async([], [], {})
        assert results == []  # No steps to execute

    def test_get_function_invalid_class(self):
        with pytest.raises(ValueError):
            self.executor.get_function('InvalidClass.method')

    def test_get_function_invalid_method(self):
        with pytest.raises(AttributeError):
            self.executor.get_function('workflow_executor_test_methods.invalid_method')

    def test_nested_parallel_threads(self):
        self.executor.config = {
            'start': {
                'parallel_threads': [
                    'workflow_executor_test_methods.step_one',
                    'nested_parallel'
                ]
            },
            'nested_parallel': {
                'parallel_threads': [
                    'workflow_executor_test_methods.step_two',
                    'workflow_executor_test_methods.step_three'
                ]
            }
        }
        kwargs = {'a': 1, 'b': 2, 'c': 3, 'd': 8}
        results = self.executor.execute_workflow(**kwargs)
        assert results == [3, [6, 7]]

    def test_nested_parallel_async(self):
        self.executor.config = {
            'start': {
                'parallel_async': [
                    'workflow_executor_test_methods.step_two',
                    'nested_parallel'
                ]
            },
            'nested_parallel': {
                'parallel_async': [
                    'workflow_executor_test_methods.step_async',
                    'workflow_executor_test_methods.step_three'
                ]
            }
        }
        kwargs = {'c': 3, 'd': 4, 'e': 2}
        results = self.executor.execute_workflow(**kwargs)
        assert results == [6, [4, 3]]

    def test_get_function_kwargs_missing_required_arg(self):
        def func(a, b):
            pass
        provided_kwargs = {'a': 1} # Missing required 'b' argument
        with pytest.raises(KeyError):
            self.executor.get_function_kwargs_with_values(func, provided_kwargs)
    
    def test_get_function_kwargs_having_default_value(self):
        def func(a, b=2):  # 'b' has a default value
            pass
        provided_kwargs = {'a': 1}  # Only 'a' is provided, 'b' will use its default value
        result = self.executor.get_function_kwargs_with_values(func, provided_kwargs)
        assert result == {'a': 1}  # 'b' is not in provided_kwargs, so it uses the default

    def test_get_function_kwargs_extra_provided(self):
        def func(a, b):
            pass
        provided_kwargs = {'a': 1, 'b': 2, 'extra': 3}
        expected = {'a': 1, 'b': 2}
        assert self.executor.get_function_kwargs_with_values(func, provided_kwargs) == expected

    def test_flatten_invalid_input(self):
        invalid_input = 123  # Non-iterable input
        with pytest.raises(TypeError):
            self.executor.flatten_tuples(invalid_input)

    @pytest.mark.parametrize("data, expected", [
        ([(Document(page_content=f"content_{uuid.uuid4()}", metadata={}), 0.5), (Document(page_content=f"content_{uuid.uuid4()}", metadata={}), 1.0)], True),
        ([(Document(page_content=f"content_{uuid.uuid4()}", metadata={}), 0.5), (1.5, 2.0)], False)
    ])
    def test_type_matching_list_of_tuples_document_float(self, data, expected):
        param_annotation = list[tuple[Document, float]]
        assert WorkflowExecutor.is_matching_type_and_subtypes(data, param_annotation) == expected

    @pytest.mark.parametrize("data, expected", [
        ((1, 2), True),
        ((1, "two"), False)
    ])
    def test_type_matching_tuple_of_ints(self, data, expected):
        param_annotation = tuple[int, int]
        assert WorkflowExecutor.is_matching_type_and_subtypes(data, param_annotation) == expected
    
    @pytest.mark.parametrize("data, expected", [
        ({"one": 1, "two": 2}, True),
        ({1: "one", 2: "two"}, False)
    ])
    def test_type_matching_dict_str_int(self, data, expected):
        param_annotation = dict[str, int]
        assert WorkflowExecutor.is_matching_type_and_subtypes(data, param_annotation) == expected

    def test_type_matching_list_of_documents(self):
        documents = [Document(page_content=f"content_{uuid.uuid4()}", metadata={}), Document(page_content=f"content_{uuid.uuid4()}", metadata={})]
        param_annotation = list[Document]
        assert WorkflowExecutor.is_matching_type_and_subtypes(documents, param_annotation)

    def test_type_matching_none_value(self):
        param_annotation = list[Document]
        assert WorkflowExecutor.is_matching_type_and_subtypes(None, param_annotation)

    def test_type_matching_empty_list(self):
        param_annotation = list[Document]
        assert WorkflowExecutor.is_matching_type_and_subtypes([], param_annotation)

    # Test use of output_name decorator in workflow_executor_test_methods
    def test_get_return_infos_for_function_single_output(self):
        def dummy_function():
            pass
        dummy_function._output_name = 'result'
        return_info = self.executor._get_return_infos_for_function(dummy_function)
        assert return_info == {'output_names': ['result']}

    def test_get_return_infos_for_function_multiple_outputs(self):
        def dummy_function():
            pass
        dummy_function._output_name = ['result1', 'result2']
        return_info = self.executor._get_return_infos_for_function(dummy_function)
        assert return_info == {'output_names': ['result1', 'result2']}

    def test_execute_function_single_output(self):
        def dummy_function(a, b):
            return a + b
        dummy_function._output_name = 'sum'
        self.executor.get_static_method = lambda x: dummy_function  # Mock method
        kwargs = {'a': 2, 'b': 3}
        self.executor.execute_function('dummy_function', [], kwargs)
        assert kwargs['sum'] == 5

    def test_execute_function_multiple_outputs(self):
        def dummy_function(a, b):
            return a + b, a * b
        dummy_function._output_name = ['sum', 'product']
        self.executor.get_static_method = lambda x: dummy_function  # Mock method
        kwargs = {'a': 2, 'b': 3}
        self.executor.execute_function('dummy_function', [], kwargs)
        assert kwargs['sum'] == 5
        assert kwargs['product'] == 6

    def test_execute_workflow_with_named_outputs(self):
        self.executor.get_static_method = lambda x: workflow_executor_test_methods.step_one_w_output_name if x == 'step_one' else workflow_executor_test_methods.step_two_w_output_name  # Mock method

        steps_config = ['step_one', 'step_two']
        kwargs = {'a': 2, 'b': 3}
        results = self.executor.execute_workflow(steps_config, kwargs_values=kwargs)
        assert kwargs['sum'] == 5
        assert kwargs['double'] == 10
        assert results == [10]

    @pytest.mark.parametrize("kwargs_value, previous_results, expected_kwargs", [
        ({'x': 1}, [1, 2, 3], {'x': 1, 'y': 2, 'z': 3}),
        ({'y': 3}, [2, 3, 4], {'x': 2, 'y': 3, 'z': 4}),
    ])
    def test_prepare_arguments_for_function(self, kwargs_value, previous_results, expected_kwargs):
        prepared_kwargs = self.executor._prepare_arguments_for_function(workflow_executor_test_methods.step_five, previous_results, kwargs_value)
        assert prepared_kwargs == expected_kwargs, f"Expected {expected_kwargs} but got {prepared_kwargs}"


    def test_prepare_arguments_simple_case(self):
        func = workflow_executor_test_methods.sample_function
        previous_results = [42, "test", 3.14]
        kwargs_value = {}

        kwargs = self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)
        assert kwargs == {'arg1': 42, 'arg2': 'test', 'arg3': 3.14}

    def test_prepare_arguments_mixed_case(self):
        func = workflow_executor_test_methods.sample_function
        previous_results = ["test", 3.14]
        kwargs_value = {'arg1': 42, 'arg3': 2.71}

        kwargs = self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)
        assert kwargs == {'arg1': 42, 'arg2': 'test', 'arg3': 2.71}

    def test_prepare_arguments_complex_case(self):
        func = workflow_executor_test_methods.sample_function
        previous_results = ["from_previous_results", 123]  # 123 is an int, type mismatch for arg4 (bool)
        kwargs_value = {'arg1': 1}

        with pytest.raises(TypeError, match="Type mismatch for argument 'arg3': expected <class 'float'>, got <class 'int'>"):
            self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)

    def test_missing_required_argument(self):
        func = workflow_executor_test_methods.sample_function
        previous_results = []
        kwargs_value = {}

        with pytest.raises(TypeError, match="Missing argument: 'arg1', which is required, because it has no default value."):
            self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)

    def test_prepare_arguments_with_defaults(self):
        func = workflow_executor_test_methods.another_function
        previous_results = [5]
        kwargs_value = {}

        kwargs = self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)
        assert kwargs == {'arg1': 5}

    def test_prepare_arguments_varargs_case(self):
        func = workflow_executor_test_methods.varargs_function
        previous_results = [10, "extra", 2.5]
        kwargs_value = {}

        kwargs = self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)
        assert kwargs == {'arg1': 10, 'arg2': 'extra', 'arg3': 2.5}

    def test_type_mismatch(self):
        func = workflow_executor_test_methods.sample_function
        previous_results = ["wrong_type", 3.14]
        kwargs_value = {}

        with pytest.raises(TypeError, match="Type mismatch for argument 'arg1': expected <class 'int'>, got <class 'str'>"):
            self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)

    def test_kwarg_override(self):
        func = workflow_executor_test_methods.sample_function
        previous_results = [42, "test"]
        kwargs_value = {'arg3': 6.28, 'arg4': False}

        kwargs = self.executor._prepare_arguments_for_function(func, previous_results, kwargs_value)
        assert kwargs == {'arg1': 42, 'arg2': 'test', 'arg3': 6.28, 'arg4': False}


# Helper class to provide methods for testing functions calling in WorkflowExecutor
class workflow_executor_test_methods:
    # Dummy functions to act as workflow steps
    def step_one(a, b):
        return a + b

    def step_two(c):
        return c * 2

    def step_three(d):
        return d - 1
    
    def step_four():
        return 7
    
    def step_five(x, y, z):
        return x + y + z
    
    
    @output_name('sum')
    def step_one_w_output_name(a, b):
        return a + b

    @output_name('double')
    def step_two_w_output_name(c):
        return c * 2
        
    @output_name('product')
    def step_three_using_output_names(sum, output_name):
        return sum * output_name

    async def step_async(e):
        await asyncio.sleep(0.1)
        return e ** 2
    
    def sample_function(arg1: int, arg2: str, arg3: float, arg4: bool = True):
        pass

    def another_function(arg1: int, arg2: str = "default", arg3: list = None):
        pass

    def varargs_function(arg1: int, *args, arg2: str = "default", arg3: float = 1.0):
        pass
