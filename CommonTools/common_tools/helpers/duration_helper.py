import re
import time
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.file_helper import file

class DurationHelper:
    def print_import_duration(import_statement: str, import_description: str = None, print_threshold: float = None) -> float:
        duration = DurationHelper.get_import_duration(import_statement)
        if duration and (not print_threshold or duration >= print_threshold):
            if not import_description: import_description = import_statement
            max_blanks = 100
            blanks = " " * (max_blanks - len(import_description)) if len(import_description) < max_blanks else ""
            #
            txt.print(f'> {import_description}:{blanks} Import duration: {duration:.2f}s.')
            return duration
        return 0

    def get_import_duration(import_statement: str) -> float:
        start = time.time()
        try:
            exec(import_statement, globals(), locals())
        except Exception as ex:
            txt.print(f"[ERROR] Fails to import: '{import_statement}': {ex}")
            return
        duration = time.time() - start
        return duration

    def print_all_imports_duration_for_file(file_path: str, include_inner_import = False, print_threshold: float = 0.7) -> None:
        txt.stop_spinner()
        start = time.time()
        last_slash_index = max(file_path.rfind('/'), file_path.rfind('\\'))
        last_dot_index = file_path.rfind('.')
        if last_dot_index == -1: last_dot_index = len(file_path)

        txt.print(f"\r\r\n## Analyzing duration for all imports from file: '{file_path[last_slash_index + 1:last_dot_index]}' ##")
        
        file_content = file.read_file(file_path)
        file_lines = file_content.splitlines()
        for file_line in file_lines:
            if include_inner_import:
                file_line = file_line.strip()
            if not file_line or file_line.startswith("#") or not (file_line.startswith("import ") or file_line.startswith("from ")):
                continue

            # Match lines starting with "import"
            if file_line.startswith("import "):
                imports_str = file_line[7:].strip()
                # Split by commas
                modules = [m.strip() for m in imports_str.split(",")]
                for module in modules:
                    if not module: continue
                    import_statement = f"import {module}"
                    import_desc = f"{module} (full)"
                    DurationHelper.print_import_duration(import_statement, import_desc, print_threshold)

            # Match lines starting with "from"
            elif file_line.startswith("from "):
                pattern = re.compile(r'^from\s+(\S+)\s+import\s+(.+)$')
                match = pattern.match(file_line)
                if match:
                    base_module = match.group(1).strip()
                    submodules_str = match.group(2).strip()
                    submodules = [s.strip() for s in submodules_str.split(",")]
                    for submod in submodules:
                        if not submod:
                            continue
                        import_statement = f"from {base_module} import {submod}"
                        import_desc = f"{submod} (from {base_module})"
                        DurationHelper.print_import_duration(import_statement, import_desc, print_threshold)
                # If the line doesn't match the pattern precisely, skip or handle advanced cases
        
        duration = time.time() - start
        txt.print(f"\r\n## Total imports duration for file: '{file_path[last_slash_index + 1:last_dot_index]}' {duration:.2f}s ##")