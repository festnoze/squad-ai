class MethodSummaryInfo:
    def __init__(self, code_start_index: int, generated_xml_summary: str = None):
        self.code_start_index: int = code_start_index
        self.generated_xml_summary: str = generated_xml_summary
    
    def to_dict(self):
        return {
            'code_start_index': self.code_start_index,
            'generated_xml_summary': self.generated_xml_summary
        }

class StructSummariesInfos:
    def __init__(self, file_path: str, index_shift_code: int, indent_level: int, generated_summary: str = None , methods: list[MethodSummaryInfo] = []):
        self.file_path: str = file_path
        self.index_shift_code: int = index_shift_code
        self.indent_level: int = indent_level
        self.generated_summary: str = generated_summary
        self.methods: list[MethodSummaryInfo] = methods

    def to_dict(self):
        return {
            'file_path': self.file_path,
            'index_shift_code': self.index_shift_code,
            'indent_level': self.indent_level,
            'generated_summary': self.generated_summary,
            'methods': [method.to_dict() for method in self.methods]
        }
