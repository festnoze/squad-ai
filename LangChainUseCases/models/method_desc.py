from models.base_desc import BaseDesc
import json

class MethodDesc(BaseDesc):
    def __init__(self, summary_lines: list[str], attributs: list[str], method_name: str, method_return_type: str, code: str, is_async: bool = False, is_task: bool = False, is_ctor: bool = False, is_static: bool = False, is_abstract: bool = False, is_override: bool = False, is_virtual: bool = False, is_sealed: bool = False, is_new: bool = False):
        super().__init__(name=method_name)
        self.method_name = method_name
        self.summary_lines = summary_lines
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

        @property
        def code_chunks(self):
            if not self._code_chunks:
                return [self.code]
            return self._code_chunks
        self.code_chunks: list[str] = None

    def to_json(self):
        return json.dumps(self.__dict__, cls=MethodDescEncoder)

class MethodDescEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, MethodDesc):
            return obj.__dict__
        return super().default(obj)
