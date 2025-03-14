from common_tools.helpers.txt_helper import txt
from common_tools.helpers.file_helper import file

class Helper:
    @staticmethod
    def flatten_inner_lists(values: list[any]) -> list[str]:
        if not values: 
            return None
        flatten_list: list[str] = []
        for item in values:
            if isinstance(item, list):
                flatten_list.extend(Helper.flatten_inner_lists(item))
            elif isinstance(item, str):
                flatten_list.append(item)
        return flatten_list
    
    @staticmethod
    def print_fields_values(extracted_values: list[dict[str, any]]) -> None:
        groups: list[str] = []
        fields: list[str] = []
        for extracted_value in extracted_values:
            for key in extracted_value.keys():
                group, field = key.split(".")
                groups.append(group)
                fields.append(field)
        max_group: int = max(len(g) for g in groups) if groups else 0
        max_field: int = max(len(f) for f in fields) if fields else 0
        if not any(extracted_values):
            txt.print("  - No values extracted from conversation -")
        for extracted_value in extracted_values:
            for key, value in extracted_value.items():
                group, field = key.split(".")
                group_str: str = f"'{group}'"
                field_str: str = f"'{field}'"
                txt.print("  - Group: " + group_str.ljust(max_group + 2) +
                    " | Field: " + field_str.ljust(max_field + 2) +
                    " | Value = '" + str(value) + "'.")
                
    @staticmethod
    def resolve_file_references(data: dict[str, any], references_files_path = '') -> dict:
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str) and value.startswith("@file:"):
                    file_path: str = value[len("@file:"):]
                    reference_file = file.get_as_yaml(references_files_path + file_path)
                    data[key] = reference_file[key]
                else:
                    data[key] = Helper.resolve_file_references(value, references_files_path)
        elif isinstance(data, list):
            for index, item in enumerate(data):
                data[index] = Helper.resolve_file_references(item, references_files_path)
        return data