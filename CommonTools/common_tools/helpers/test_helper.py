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
    def create_dynamic_fake_class_of(real_class, fake_class_name, override_methods=None):
        if override_methods is None:
            override_methods = {}

        class_attributes = {}
        for name, method in inspect.getmembers(real_class, predicate=inspect.isfunction):
            if name in override_methods:
                # Utiliser la fonction de remplacement fournie
                class_attributes[name] = override_methods[name]
            elif name.endswith('_async'):
                async def _mock_async_method(*args, **kwargs):
                    yield f"Mocked {name} called"
                class_attributes[name] = _mock_async_method
            else:
                def _mock_method(*args, **kwargs):
                    return f"Mocked {name} called"
                class_attributes[name] = _mock_method

        FakeClass = type(fake_class_name, (object,), class_attributes)
        return FakeClass