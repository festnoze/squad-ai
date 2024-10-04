from concurrent.futures import ThreadPoolExecutor, as_completed
import inspect
#
from common_tools.helpers.file_helper import file
from common_tools.helpers.ressource_helper import Ressource
from common_tools.helpers.txt_helper import txt


class WorkflowExecutor:
    def __init__(self, config_file_path:str = None):
        if config_file_path:
            self.config = file.get_as_yaml(config_file_path)
        else:
            self.config = Ressource.get_rag_pipeline_default_config_1()
        self.previous_results = []  # Used to store dynamic steps' results

    def execute_workflow(self, first_step_name, **kwargs):
        
        results = {}

        first_step = self.config[first_step_name]
        if isinstance(first_step, dict) and 'parallel' in first_step:
            # Parallel execution
            futures = {}
            parallel_results = {}
            with ThreadPoolExecutor() as executor:
                for parallel_step in first_step['parallel']:
                    futures[parallel_step] = executor.submit(self._run_step, parallel_step, *results.get('previous', []))
                
                # Collect all parallel results
                for step_name, future in futures.items():
                    parallel_results[step_name] = future.result()
                results = tuple(parallel_results.values())
        else:
            # Sequential execution
            step_name = first_step if isinstance(first_step, str) else first_step['name']
            result = self._run_step(step_name, *results.get('previous', []))
            results = [result]
        
        return results

    def _run_step(self, step_name, *args, **kwargs):
        class_name, method_name = step_name.split('.')
        step_class = globals()[class_name]
        step_method = getattr(step_class, method_name)
        return step_method(*args, **kwargs)
    
    def get_required_args(self, func):
        """
        Inspects a function and returns a dictionary of the required arguments
        filtered from the available kwargs.
        """
        sig = inspect.signature(func)
        required_args = {}
        
        # Iterate through the function parameters and match with kwargs
        for param_name, param in sig.parameters.items():
            if param_name in self.kwargs:
                required_args[param_name] = self.kwargs[param_name]
        return required_args