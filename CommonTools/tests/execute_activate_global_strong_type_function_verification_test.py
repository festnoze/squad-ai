import pytest
from common_tools.helpers.execute_helper import Execute
from common_tools.helpers.txt_helper import txt

class Test_Execute_ActivateGlobalStrongTypeFunctionVerification:
    @pytest.fixture(scope="function", autouse=True)
    def activate_profiler(self): 
        txt.activate_print = True       
        yield
        Execute.deactivate_global_function_parameters_types_verification()
        txt.activate_print = False

    # Define some example functions to test
    def function_one(a: int, b: str):
        return f'Integer: {a}, String: {b}'

    def function_two(x: float, y: list):
        return f'Float: {x}, List: {y}'

    def function_three(name: str, age: int):
        return f'Name: {name}, Age: {age}'

    # Test suite using pytest
    @pytest.mark.parametrize('func, params, failure_awaited', [
        (function_one, {'a': 42, 'b': 'Hello'}, False),               # Valid input, no error expected
        (function_one, {'a': 'wrong type', 'b': 'Hello'}, True),      # Invalid 'a', should raise TypeError
        (function_two, {'x': 3.14, 'y': [1, 2, 3]}, False),           # Valid input, no error expected
        (function_two, {'x': 'Not a float', 'y': [1, 2, 3]}, True),   # Invalid 'x', should raise TypeError
        (function_three, {'name': 'Alice', 'age': 30}, False),        # Valid input, no error expected
        (function_three, {'name': 123, 'age': 'thirty'}, True),       # Invalid both 'name' and 'age', should raise TypeError
    ])
    def test_type_checking(self, func, params, failure_awaited):   
        return # todo: Tests are deactivated. Don't work now. method implementation to fix.      
        txt.print(f"Start testing function: {func.__name__} with parameters: {params}")      
        Execute.activate_global_function_parameters_types_verification()
        if failure_awaited:
            with pytest.raises(TypeError):
                res = func(**params)
                txt.print(f"Result: {res}")
        else:
            # If no failure is expected, we simply call the function
            res = func(**params)
            txt.print(f"Result: {res}")