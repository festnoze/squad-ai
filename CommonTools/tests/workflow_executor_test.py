import asyncio
import pytest
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

    def test_flatten(self):
        nested_list = [1, [2, [3, 4], 5], 6, 'string', (7, 8)]
        expected = [1, 2, 3, 4, 5, 6, 'string', 7, 8]
        result = self.executor.flatten(nested_list)
        assert result == expected

    def test_flatten_complex(self):
        nested = [1, ['a', [True, [3.14, None]]], {'key': 'value'}]
        expected = [1, 'a', True, 3.14, None, {'key': 'value'}]
        result = self.executor.flatten(nested)
        assert result == expected

    def test_execute_step_first_step(self):
        kwargs = {'a': 1, 'b': 2}
        result = self.executor.execute_function('workflow_executor_test_methods.step_one', [], kwargs)
        assert result == 3

    def test_execute_step_subsequent_step(self):
        previous_results = [3]
        result = self.executor.execute_function('workflow_executor_test_methods.step_two', previous_results, {})
        assert result == 6

    def test_execute_workflow_single_step(self):    
        steps_config = ['workflow_executor_test_methods.step_one']
        kwargs = {'a': 2, 'b': 3}
        results = self.executor.execute_workflow(steps_config, **kwargs)
        assert results == [5]

    def test_execute_workflow_sequential_steps(self):
        steps_config = [
            'workflow_executor_test_methods.step_one', 
            'workflow_executor_test_methods.step_two', 
            'workflow_executor_test_methods.step_three'
        ]
        kwargs = {'a': 2, 'b': 3}
        results = self.executor.execute_workflow(steps_config, **kwargs)
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
        results = self.executor.execute_workflow(steps_config, **kwargs)
        assert results == [5, 4]

    def test_execute_workflow_parallel_async(self):
        steps_config = [{'parallel_async': ['workflow_executor_test_methods.step_async', 'workflow_executor_test_methods.step_three']}]
        kwargs = {'e': 3, 'd': 10}
        results = self.executor.execute_workflow(steps_config, **kwargs)
        assert results == [9, 9]

    def test_execute_workflow_nested_steps(self):
        self.executor.config = {
            'nested_steps': ['workflow_executor_test_methods.step_two', 'workflow_executor_test_methods.step_three']
        }
        steps_config = ['workflow_executor_test_methods.step_one', 'nested_steps']
        kwargs = {'a': 2, 'b': 3}
        results = self.executor.execute_workflow(steps_config, **kwargs)
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
        results = self.executor.execute_workflow(self_config, None, 'sub1', **kwargs)
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
        results = self.executor.execute_workflow(steps_config, **kwargs)
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

    # def test_using_splitted_previous_results(self):
    #     previous_results = [3, 2]
    #     config = ['workflow_executor_test_methods.step_two', 'workflow_executor_test_methods.step_two']
    #     result = self.executor.execute_workflow(config, previous_results, {})
    #     assert result == [6, 4]

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
            self.executor.flatten(invalid_input)


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

    async def step_async(e):
        await asyncio.sleep(0.1)
        return e ** 2
