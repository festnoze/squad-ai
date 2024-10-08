import inspect
from unittest.mock import Mock

class TestHelper:
    @staticmethod
    def create_mock_class_of(real_class):
        fake_class = Mock()

        # Inspect methods of the real class
        for name, method in inspect.getmembers(real_class, predicate=inspect.isfunction):
            # Add the same method names with default return values to the fake class
            setattr(fake_class, name, Mock(return_value=f"{name} called"))

        return fake_class

    @staticmethod
    def create_dynamic_fake_class_of(real_class, fake_class_name):
        class_attributes = {}
        for name, method in inspect.getmembers(real_class, predicate=inspect.isfunction):
            def _mock_method(*args, **kwargs):
                return f"Mocked {name} called"
            class_attributes[name] = _mock_method

        # Dynamically create the class with the specified name
        FakeClass = type(fake_class_name, (object,), class_attributes)

        return FakeClass