from langchain.tools import tool
from models.form import Form
from models.group import Group
from models.field import Field
from common_tools.helpers.file_helper import file
from common_tools.helpers.llm_helper import Llm
from common_tools.langchains.langchain_factory import LangChainFactory


# ================== Définition des Outils ==================

@tool
def load_form_from_yaml(file_path: str) -> Form:
    """Charge un formulaire depuis un fichier YAML."""
    yaml_data = file.get_as_yaml(file_path)
    return create_form_from_yaml(yaml_data)

def create_form_from_yaml(yaml_data: dict[str, any]) -> Form:
    """Crée un objet Form à partir des données YAML."""
    groups = []
    for group_data in yaml_data['form']['groups']:
        fields = [
            Field(
                name=field_data['name'],
                description=field_data['description'],
                type=field_data['type'],
                min_size_or_value=field_data.get('min_size_or_value'),
                max_size_or_value=field_data.get('max_size_or_value'),
                regex=field_data.get('regex'),
                regex_description=field_data.get('regex_description'),
                optional=field_data.get('optional'),
                default_value=field_data.get('default_value'),
                allowed_values=field_data.get('allowed_values'),
                validation_func_name= field_data.get('validation_func_name'),
            )
            for field_data in group_data['fields']
        ]
        groups.append(Group(name=group_data['name'], description=group_data['description'], fields=fields))
    return Form(name=yaml_data['form']['name'], groups=groups)

@tool
def extract_values_from_conversation(conversation: str, form: Form) -> dict[str, any]:
    """Analyse la conversation et extrait les valeurs correspondant aux champs du formulaire."""
    extracted_values = {}  # Simuler extraction basée sur conversation
    for group in form.groups:
        for field in group.fields:
            if field.name in conversation:  # Simple logique de détection
                extracted_values[field.name] = f"Valeur détectée pour {field.name}"
    return extracted_values

@tool
def generate_question_for_group(group: Group) -> str:
    """Génère une question pour remplir un groupe de champs."""
    prompt = file.get_as_str("src/prompts/group_query_for_values_prompt.txt")
    fields_infos = "\n".join([f"{field.name}: {field.description}" for field in group.fields])
    return prompt.replace("{group_name}", group.name).replace("{fields_infos}", fields_infos)

@tool
def generate_question_for_field(field: Field) -> str:
    """Génère une question pour un champ individuel en cas d'erreur ou de correction."""
    prompt = file.get_as_str("src/prompts/query_fixing_single_field_prompt.txt")
    return prompt.replace("{field_name}", field.name).replace("{field_desc}", field.description)

@tool
def interpret_user_response(user_response: str, group: Group) -> dict[str, any]:
    """Interprète une réponse utilisateur pour extraire les valeurs d'un groupe."""
    return {field.name: f"Valeur extraite: {user_response}" for field in group.fields}

@tool
def fill_form(form: Form, extracted_values: dict[str, any]) -> Form:
    """Remplit le formulaire avec les valeurs validées."""
    for group in form.groups:
        for field in group.fields:
            if field.name in extracted_values:
                field.value = extracted_values[field.name]
    return form

@tool
def validate_form(form: Form) -> str:
    """Valide le formulaire et retourne 'ok' ou 'erreur'."""
    return "ok" if form.validate().is_valid else "erreur"
