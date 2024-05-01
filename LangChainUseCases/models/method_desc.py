from models.base_desc import BaseDesc

class MethodDesc(BaseDesc):
    def __init__(self, summary: str, attributs: list[str], method_name: str, method_return_type: str, code: str, is_async: bool = False, is_task: bool = False, is_ctor: bool = False, is_static: bool = False, is_abstract: bool = False, is_override: bool = False, is_virtual: bool = False, is_sealed: bool = False, is_new: bool = False):
        super().__init__(name=method_name)
        self.method_name = method_name
        self.summary = summary
        self.attributs = attributs
        self.method_return_type = method_return_type
        self.code = code
        self.is_async = is_async
        self.is_task = is_task
        self.is_ctor = is_ctor
        self.is_static = is_static
        self.is_abstract = is_abstract
        self.is_override = is_override
        self.is_virtual = is_virtual
        self.is_sealed = is_sealed
        self.is_new = is_new
        #
        self.code_chunks: list[str] = []
    
    def __str__(self):
        return f"Name: '{super.name}'"
