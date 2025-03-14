
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

    async def extract_values_from_conversation_async(conversation: str, form: Form) -> dict[str, any]:
        """Analyze the conversation and extract values corresponding to form fields."""
        results = await FormTools.llm_service.get_form_values_from_conversation_async(conversation, form)
        return results
    
    def get_group_fields(form: Form, items_to_find_dict: dict[str, any]) -> list[Field]:
        """Get the specified fields of the form's group."""
        fields_list = []
        for group in form.groups:
            if group.name == items_to_find_dict["group"]:
                for field in group.fields:
                    for field_to_find in items_to_find_dict["fields"]:
                        if field.name == field_to_find['name']:
                            fields_list.append(field)
        return fields_list
    
    def get_missing_groups_and_fields(form: Form) -> list[dict[str, any]]:
        missing_groups_and_fields: list[dict[str, any]] = []
        for group in form.groups:
            if any(not field.is_valid for field in group.fields):
                invalid_or_optional_fields = [field for field in group.fields if not field.is_valid or field.optional]
                invalid_or_optional_fields_dict = []
                for field in invalid_or_optional_fields:
                    errors = '. '.join([error.message for error in field.validation_result.errors])
                    if field.optional: errors = "la fourniture d'une valeur pour ce champ est optionelle."
                    invalid_or_optional_fields_dict.append({'name': field.name, 'value': field.value if field.value else None, 'errors': errors})
                missing_groups_and_fields.append({'group': group.name, 'fields': invalid_or_optional_fields_dict})
        return missing_groups_and_fields

    async def generate_question_for_group_fields_async(group_fields: list[Field]) -> str:
        """Generate a question for filling a group of fields."""
        return await FormTools.llm_service.get_question_for_group_fields_values_async(group_fields)

    async def generate_question_for_single_field_async(field: Field) -> str:
        """Generate a question for an individual field."""
        return await FormTools.llm_service.get_question_to_fix_field_value_async(field)

    async def interpret_user_response_async(targeted_fields: list[Field], user_answer) -> dict[str, any]:
        """Interpret user response to extract field values."""
        if len(targeted_fields) > 1:
            values = await FormTools.llm_service.get_group_fields_values_from_answer_async(targeted_fields, user_answer)
        else:
            values = [user_answer]
        return values
    
    def link_values_with_fields(values: dict[str, any], targeted_fields: list[Field]) -> dict[str, any]:
        """Link extracted values with form fields."""        
        linked_values = [{ f'{targeted_field.group.name}.{targeted_field.name}': values[i] } for i, targeted_field in enumerate(targeted_fields)]
        return linked_values
    
    def fill_form_with_provided_values(form: Form, fields_values_to_integrate: list[dict]) -> Form:
        """Fill the form with the provided values (with keys like: 'group_name.field_name')."""
        if not fields_values_to_integrate or not any(fields_values_to_integrate):
            return form
        extracted_values_count = len(fields_values_to_integrate)
        setted_values_count = 0
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
        """return 'ok' if form is valide else 'error'."""
        return "ok" if form.is_valid else "error"