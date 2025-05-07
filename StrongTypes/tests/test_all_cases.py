
import pytest
from strong_types.analyzer import run_static_analysis
from strong_types.decorators import strong_type
from typing import Union

class Demo:
    @strong_type
    def add(self, x: int, y: int) -> int:
        return x + y

    def wrong_return(self, x: int) -> str:
        return x + 1  # should fail

    def cascade_chain(self, a: int) -> str:
        b = self.add(a, 1)
        return str(b)

    def wrong_chain(self, a: int) -> str:
        b = self.add(a, 1)
        return b  # should fail (int vs str)

    def call_with_wrong_type(self):
        return self.add("a", 3)  # should fail

def test_add_passes():
    run_static_analysis(Demo.add)

def test_wrong_return_fails():
    with pytest.raises(AssertionError):
        run_static_analysis(Demo.wrong_return)

def test_cascade_chain_passes():
    run_static_analysis(Demo.cascade_chain)

def test_wrong_chain_fails():
    with pytest.raises(AssertionError):
        run_static_analysis(Demo.wrong_chain)

def test_call_with_wrong_type_fails():
    with pytest.raises(AssertionError):
        run_static_analysis(Demo.call_with_wrong_type)
