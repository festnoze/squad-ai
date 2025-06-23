import yaml
import json
import os
#from api_validator import APIValidator

def load_config():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    config_path = os.path.join(project_root, 'app/agents/configs/lid_api_config.yaml')
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)

def test_lead_injection():
    # Charger la configuration
    config = load_config()
    
    # Exemple de requête valide
    valid_request = {
        "email": "test@example.com",
        "nom": "Dupont",
        "prenom": "Jean",
        "tel": "+33123456789",
        "formulaire": "formation-test",
        "url": "https://example.com",
        "utm_source": "test",
        "utm_medium": "CORE_PKL_Email",
        "pays": "FR",
        "thematique": "Marketing",
        "form_area": "CORE_PKL_Content"
    }
    return
    # Créer une instance du validateur
    validator = APIValidator(config)
    
    # Tester la requête valide
    print("\nTest de requête valide:")
    result = validator.validate_request("lead_injection", valid_request)
    print(f"Résultat: {json.dumps(result, indent=2)}")
    
    # Exemple de requête invalide (manque de champs requis)
    invalid_request = {
        "email": "test@example.com",
        "nom": "Dupont"
    }    
    
    # Tester la requête invalide
    print("\nTest de requête invalide:")
    result = validator.validate_request("lead_injection", invalid_request)
    print(f"Résultat: {json.dumps(result, indent=2)}")