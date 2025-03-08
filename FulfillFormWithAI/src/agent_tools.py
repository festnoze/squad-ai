
# ================== Définition des Outils ================== #

#from langchain.tools import tool
from models.form import Form
from models.group import Group
from models.field import Field
from common_tools.models.llm_info import LlmInfo
from llm_service import LlmService

class FormTools:
    llm_service:LlmService

    def init(llms_infos: list[LlmInfo]):
        FormTools.llm_service = LlmService(llms_infos)

    def extract_values_from_conversation(conversation: str, form: Form) -> dict[str, any]:
        """Analyze the conversation and extract values corresponding to form fields."""
        extracted_values = {}
        for group in form.groups:
            for field in group.fields:
                if field.name in conversation:
                    extracted_values[field.name] = f"Extracted value for {field.name}"
        return extracted_values
    
    def find_form_item(form: Form, item_to_find_dict: dict[str, any]) -> any:
        for group in form.groups:
            if group.name == item_to_find_dict["group"]:
                if item_to_find_dict["field"] is None:
                    return group
                else:
                    for field in group.fields:
                        if field.name == item_to_find_dict["field"]:
                            return field
        return None
    
    def get_missing_groups_and_fields(form: Form) -> list[dict[str, any]]:
        missing_groups_and_fields: list[dict[str, any]] = []
        for group in form.groups:
            if all(not field.is_validated for field in group.fields):
                missing_groups_and_fields.append({'group': group.name, 'field': None, 'value': None})
            else:
                for field in group.fields:
                    if not field.is_validated:
                        missing_groups_and_fields.append({'group': group.name, 'field': field.name, 'value': field.value if field.value else None})
        return missing_groups_and_fields

    async def generate_question_for_group_async(group: Group) -> str:
        """Generate a question for filling a group of fields."""
        return await FormTools.llm_service.get_question_for_group_values_async(group)

    async def generate_question_for_field_async(field: Field) -> str:
        """Generate a question for an individual field."""
        return await FormTools.llm_service.get_question_to_fix_field_value_async(field)

    async def interpret_user_response_async(form_item, user_answer) -> dict[str, any]:
        """Interpret user response to extract field values."""
        if isinstance(form_item, Group):
            values = await FormTools.llm_service.get_group_values_from_text_async(form_item, user_answer)
        elif isinstance(form_item, Field):
            values = [user_answer]
        return values
    
    def link_values_with_fields(values: dict[str, any], form_item) -> dict[str, any]:
        """Link extracted values with form fields."""
        i = 0
        linked_values = []
        if isinstance(form_item, Group):
            if len(values) != len(form_item.fields):
                raise ValueError("Number of values does not match the number of fields in the group.")
            for field in form_item.fields:
                linked_values.append({ f'{form_item.name}.{field.name}': values[i] })
                i += 1
        if isinstance(form_item, Field):
            linked_values = [{ f'{form_item.group_name}.{form_item.name}': values[0] }] #TODO: cannot work, because form_item isn't the group name, need to be fixed
        return linked_values

    
    def fill_form_with_provided_values(form: Form, fields_values_to_integrate: list[dict]) -> Form:
        """Fill the form with the provided values."""
        extracted_values_count = len(fields_values_to_integrate)
        setted_values_count = 0        
        if extracted_values_count == 0: return form
        extracted_values_keys = [list(d.keys())[0] for d in fields_values_to_integrate]
        for group in form.groups:
            for field in group.fields:
                extracted_value_key = f'{group.name}.{field.name}'
                if extracted_value_key in extracted_values_keys:
                    value = None
                    for extracted_value in fields_values_to_integrate:
                        if extracted_value_key in extracted_value:
                            value = extracted_value[extracted_value_key]
                            break
                    if (value != None and value != 'null') or field.optional:
                        field.value = value
                    setted_values_count += 1

        if setted_values_count != extracted_values_count:
            raise ValueError("Not all extracted values were set in the form.")
        return form
    
    def validate_form(form: Form) -> str:
        """Validate the form and return 'ok' or 'error'."""
        return "ok" if form.validate().is_valid else "error"
