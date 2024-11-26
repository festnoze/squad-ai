import importlib
import inspect
import typing


class Reflexion:
    @staticmethod
    def get_function_by_name_dynamic(step_name):
        """
        Given a string like 'RAGPreTreatment.analyse_query_language', return the corresponding function.
        """
        module_name, func_name = step_name.rsplit('.', 1)
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        return func
    
    @staticmethod
    def get_static_method(class_and_function_name:str, available_classes:dict):
        """
        Retrieve a function or class method based on a string name.
        
        The format should be 'Class.method', where Class is one of the pre-imported classes.
        """
        parts = class_and_function_name.split('.')
        if len(parts) != 2: 
            raise ValueError(f"Invalid function name '{class_and_function_name}'. It should be in 'Class.method' format.")
        class_name, method_name = parts
        
        cls = available_classes.get(class_name)
        if not cls:
            raise ValueError(f"Class '{class_name}' not found.")
        
        # Check if the method exists in the class
        method = getattr(cls, method_name, None)
        if method is None or not callable(method):
            raise AttributeError(f"Class '{class_name}' does not have a callable method '{method_name}'.")
        
        return method
    
    @staticmethod
    def get_instance_method(class_and_function_name:str, available_classes:dict, instance:any = None):
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
        cls = available_classes.get(class_name)
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
        elif not isinstance(method, staticmethod):
            # Instantiate the class if no instance is provided
            instance = cls()
            return getattr(instance, method_name)
        elif isinstance(method, staticmethod):
            return Reflexion.get_static_method(class_and_function_name, available_classes)

        # For static methods, simply return the method
        return method

    @staticmethod
    def get_method_matching_params_from_provided_values(func, provided_kwargs_values):
        """
        Inspects a function and returns a dictionary of the required arguments
        filtered from the available kwargs. Raises KeyError if a required 
        argument without a default value is missing.
        """
        sig = inspect.signature(func)
        required_args = {}
        for param_name, param in sig.parameters.items():
            if param.default == inspect.Parameter.empty and param_name not in provided_kwargs_values:
                raise KeyError(f"Missing required argument: {param_name}")
            if param_name in provided_kwargs_values:
                required_args[param_name] = provided_kwargs_values[param_name]

        return required_args
    
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
                return all(Reflexion.is_matching_type_and_subtypes(item, args[0]) for item in arg_value)
            elif origin is tuple:
                return all(Reflexion.is_matching_type_and_subtypes(item, args[i]) for i, item in enumerate(arg_value))
            else:
                raise ValueError(f"Unhandled origin type: {origin}")
        
        if origin is dict:
            return isinstance(arg_value, dict) and (not args or all(
                Reflexion.is_matching_type_and_subtypes(k, args[0]) and 
                Reflexion.is_matching_type_and_subtypes(v, args[1])
                for k, v in arg_value.items()
            ))

        return isinstance(arg_value, origin or param_annotation)
