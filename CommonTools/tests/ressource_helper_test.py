import pytest
from common_tools.helpers.ressource_helper import Ressource

## NOT TESTED
class TestReplaceVariables:
    
    @pytest.mark.parametrize("prompt, variables, expected", [
        ("Hello {name}", {"name": "John"}, "Hello John"),
        ("Your total is {amount}", {"amount": "100"}, "Your total is 100"),
        ("Goodbye {name}", {"name": "Alice"}, "Goodbye Alice")
    ])
    def test_replace_recognized_variable(self, prompt: str, variables: dict, expected: str):
        result = Ressource.replace_variables(prompt, variables)
        assert result == expected

    @pytest.mark.parametrize("prompt, variables, expected", [
        ("Hello {unknown}", {}, "Hello "),
        ("Goodbye {nonexistent_var}", {"name": "Test"}, "Goodbye "),
        ("Hello {name} and {unknown_var}", {"name": "John"}, "Hello John and ")
    ])
    def test_remove_unmatched_variables(self, prompt: str, variables: dict, expected: str):
        result = Ressource.replace_variables(prompt, variables)
        assert result == expected

    @pytest.mark.parametrize("prompt, variables, expected", [
        ("Hello {{name}}", {"name": "John"}, "Hello {{name}}"),
        ("Your total is {{amount}} dollars", {"amount": "100"}, "Your total is {{amount}} dollars"),
        ("Use {{config}} to setup", {"config": "advanced"}, "Use {{config}} to setup")
    ])
    def test_ignore_double_curly_braces(self, prompt: str, variables: dict, expected: str):
        result = Ressource.replace_variables(prompt, variables)
        assert result == expected
