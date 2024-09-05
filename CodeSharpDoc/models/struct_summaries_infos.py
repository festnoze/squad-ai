class MethodSummaryInfo:
    def __init__(self, code_start_index: int, summary: str = None):
        self.code_start_index: int = code_start_index
        self.summary: str = summary
    
    def to_dict(self):
        return {
            'code_start_index': self.code_start_index,
            'summary': self.summary
        }

class StructSummariesInfos:
    def __init__(self, file_path: str, index_shift_code: int, indent_level: int, summary: str = None , methods: list[MethodSummaryInfo] = []):
        self.file_path: str = file_path
        self.index_shift_code: int = index_shift_code
        self.indent_level: int = indent_level
        self.summary: str = summary
        self.methods: list[MethodSummaryInfo] = methods

    def to_dict(self):
        return {
            'file_path': self.file_path,
            'index_shift_code': self.index_shift_code,
            'indent_level': self.indent_level,
            'summary': self.summary,
            'methods': [method.to_dict() for method in self.methods]
        }
