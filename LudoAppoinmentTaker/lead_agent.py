import json
import yaml
import os
import requests
from openai import OpenAI

class LeadAgent:
    def __init__(self, config_path="lid_api_config.yaml"):
        """Initialise l'agent avec la configuration YAML."""
        try:
            with open(config_path, 'r') as file:
                self.config = yaml.safe_load(file)
            
            # Vérifier la structure de la configuration
            if not self.config or 'api' not in self.config or 'endpoints' not in self.config['api']:
                raise ValueError("La configuration YAML doit contenir une section 'api.endpoints'")
            
            if 'lead_injection' not in self.config['api']['endpoints']:
                raise ValueError("La configuration YAML doit contenir un endpoint 'lead_injection'")
            
            # Initialiser le client OpenAI avec la configuration
            openai_config = self.config['api'].get('openai', {})
            api_key = openai_config.get('api_key', '')
            
            # Remplacer la variable d'environnement si présente
            if '${OPENAI_API_KEY}' in api_key:
                env_key = os.getenv('OPENAI_API_KEY')
                if not env_key:
                    raise ValueError("La variable d'environnement OPENAI_API_KEY n'est pas définie")
                api_key = api_key.replace('${OPENAI_API_KEY}', env_key)
            
            if not api_key:
                raise ValueError("La clé API OpenAI n'est pas définie dans la configuration")
            
            # Initialiser le client OpenAI avec la version 1.12.0
            self.client = OpenAI(api_key=api_key)
            
            self.model = openai_config.get('model', 'gpt-4-turbo')
            self.temperature = openai_config.get('temperature', 0.1)
            self.max_tokens = openai_config.get('max_tokens', 500)

            self.extracted_info = {}
            self.missing_fields = []
            self.request_data = []
            
        except FileNotFoundError:
            raise FileNotFoundError(f"Le fichier de configuration {config_path} n'existe pas")
        except yaml.YAMLError as e:
            raise ValueError(f"Erreur dans le format du fichier YAML: {str(e)}")
        except Exception as e:
            raise Exception(f"Erreur lors de l'initialisation de l'agent: {str(e)}")
    
    def analyze_text(self, text):
        """Analyse le texte et extrait les informations pertinentes."""
        try:
            # Extraire les informations avec le LLM
            print(text)
            new_extracted_info = self._extract_info_with_llm(text)
            print(new_extracted_info)
            self.extracted_info = {**self.extracted_info,**new_extracted_info}
            print(self.extracted_info)
            # Identifier les champs manquants
            missing_fields = self._get_missing_fields(self.extracted_info)
            
            # Formater la requête avec les valeurs par défaut
            request_data = self._format_request(self.extracted_info)
        
            # Valider la requête
            is_valid, error_message = self._validate_request(request_data)
            print("est valide : "+str(is_valid))
   
            self.missing_fields = missing_fields
            self.request_data = request_data
            self.is_valid = is_valid
            self.error_message = error_message

            if self.is_valid == False:
                        print("Toutes les informations ne sont pas présentes")
                        infosManquantes = ""
                        #Rrecup des infos manquantes
                        for field in self.missing_fields:
                                infosManquantes += field["description"] + ", " 
                        reponseText = f"""
                        Pourriez vous me donner les informations manquantes ? Les voici : {infosManquantes}
                        """
            else:
                result = self.send_request(self.request_data)
                if result.status_code == 200:
                    reponseText = f"""
                    Vous êtes bien enregistré, un conseiller en formation va vous rappeler au plus vite. Passez une bonne journée de la part de Studi.
                    """
                else:
                    reponseText = f"""
                    Désolé, une erreur est survenue lors de la création de votre fiche. Veuillez rappeler plus tard.
                    """
            return reponseText
        except Exception as e:
            print(e)
            return {
                "extracted_info": {},
                "missing_fields": [],
                "request_data": {},
                "is_valid": False,
                "error_message": f"Erreur lors de l'analyse: {str(e)}"
            }
    
    def _extract_info_with_llm(self, text):
        """Extrait les informations du texte en utilisant un LLM."""
        try:
            # Récupérer la configuration de l'endpoint
            endpoint_config = self.config.get('api', {}).get('endpoints', {}).get('lead_injection', {})
            if not endpoint_config:
                raise ValueError("Configuration de l'endpoint 'lead_injection' non trouvée")
            
            # Générer la description des champs à partir de la configuration
            fields_description = []
            
            # Ajouter les champs requis
            required_fields = endpoint_config.get('required_fields', {})
            for field, field_info in required_fields.items():
                field_type = field_info.get('type', 'string')
                description = field_info.get('description', '')
                fields_description.append(f"- {field}: {field_type} - {description} (requis)")
            
            # Ajouter les champs optionnels
            optional_fields = endpoint_config.get('optional_fields', {})
            for field, field_info in optional_fields.items():
                field_type = field_info.get('type', 'string')
                description = field_info.get('description', '')
                fields_description.append(f"- {field}: {field_type} - {description} (optionnel)")
            
            # Ajouter les valeurs énumérées si présentes
            enum_values = []
            for field, values in endpoint_config.get('enum_values', {}).items():
                enum_values.append(f"- {field}: {', '.join(values)}")
            
            # Construire le prompt
            prompt = f"""
            Tu es un assistant vocal chargé d'extraire les informations suivantes : prénom, nom, email et numéro de téléphone.
            Tu vas recevoir un texte issu d’une transcription automatique de voix. Ce texte peut contenir des erreurs typiques de reconnaissance vocale, comme :

            des adresses e-mail mal reconnues (et au lieu de @, otmel au lieu de hotmail, frr au lieu de .fr, etc.)

            des lettres épelées séparées par des espaces, des erreurs de transcription phonétique (a → ha, j → gé)

            des noms de famille épelés ou mal compris

            Ta mission est de :

            1. Trouver et corriger toute adresse e-mail
            Identifier les tentatives de mention d'une adresse e-mail (même déformée ou épelée)

            Corriger les noms de domaine courants, les séparateurs (et → @, point → ., etc.)

            Fusionner la version prononcée et la version épelée si besoin

            2. Identifier et reconstruire les noms de famille
            Détecter les noms de famille mentionnés dans des contextes comme :

            "mon nom c’est [NOM]"

            "ça s’écrit [lettres]"

            "avec un d à la fin", "comme Dupont mais sans le t"

            parfois le nom est épelé en entier, juste après avoir été prononcé en entier et mal transcrit.
            exemple : "je m'appelle Barbara Groser, G-R-A-U-S-E-R." le nom de famille à extraire est Grauser.

            Reconstituer le nom de famille avec orthographe correcte même s’il est partiellement ou totalement épelé

            Associer une épellation à un nom déjà détecté s’il y a correspondance

            3. Sortie attendue :
             Si tu ne trouve pas les champs, ne les invente pas !
            Voici la liste des champs à extraire :
            {chr(10).join(fields_description)}
            """
            
            # Ajouter les valeurs énumérées si présentes
            if enum_values:
                prompt += f"""
                Valeurs acceptées pour certains champs:
                {chr(10).join(enum_values)}
                
                """
            
            # Ajouter le texte à analyser
            prompt += f"""

            Transforme le numéro de téléphone en format sans espaces.

         
            
            Réponse (uniquement l'objet JSON, sans autre texte):
            """
            
            # Appeler l'API OpenAI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            # Extraire la réponse JSON
            response_text = response.choices[0].message.content.strip()
            
            # Nettoyer la réponse pour s'assurer qu'elle est un JSON valide
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            # Parser le JSON
            extracted_info = json.loads(response_text)
            
            # Filtrer les valeurs vides ou nulles
            return {k: v for k, v in extracted_info.items() if v and v.strip()}
            
        except Exception as e:
            print(f"Erreur lors de l'extraction avec le LLM: {str(e)}")
            return {}
    
    def _get_missing_fields(self, extracted_info):
        """Identifie les champs obligatoires manquants qui doivent être demandés à l'utilisateur."""
        try:
            endpoint_config = self.config.get('api', {}).get('endpoints', {}).get('lead_injection', {})
            if not endpoint_config:
                raise ValueError("Configuration de l'endpoint 'lead_injection' non trouvée")
            
            missing_fields = []
            required_fields = endpoint_config.get('required_fields', {})
            
            
            
            for field, field_info in required_fields.items():
                # Vérifier si le champ est manquant et doit être demandé dans la conversation
                if field not in extracted_info and field_info.get('ask_in_conversation', False):
                    missing_fields.append({
                        'name': field,
                        'description': field_info.get('description', ''),
                        'type': field_info.get('type', 'string')
                    })
            
            return missing_fields
        except Exception as e:
            print(f"Erreur lors de la vérification des champs manquants: {str(e)}")
            return []
    
    def _format_request(self, extracted_info):
        """Formate la requête avec les valeurs par défaut pour les champs manquants."""
        request_data = extracted_info.copy()
        if "tel" in request_data and isinstance(request_data["tel"], str):
            request_data["tel"] = request_data["tel"].replace(" ", "")
        
        # Récupérer la configuration de l'endpoint
        endpoint_config = self.config.get('api', {}).get('endpoints', {}).get('lead_injection', {})
        
        # Ajouter les valeurs par défaut pour les champs requis manquants
        required_fields = endpoint_config.get('required_fields', {})
        for field, field_info in required_fields.items():
            if field not in request_data and 'default' in field_info:
                request_data[field] = field_info['default']
        
        return request_data
    
    def _validate_request(self, request_data):
        """Valide la requête en fonction de la configuration."""
        try:
            endpoint_config = self.config.get('api', {}).get('endpoints', {}).get('lead_injection', {})
            if not endpoint_config:
                return False, "Configuration de l'endpoint 'lead_injection' non trouvée"
            
            # Vérifier les champs requis
            required_fields = endpoint_config.get('required_fields', {})
            for field in required_fields:
                if field not in request_data:
                    return False, f"Champ requis manquant: {field}"
            
            # Vérifier les types de données
            field_types = endpoint_config.get('field_types', {})
            for field, value in request_data.items():
                if field in field_types:
                    expected_type = field_types[field]
                    if expected_type == 'string' and not isinstance(value, str):
                        return False, f"Le champ '{field}' doit être une chaîne de caractères"
                    elif expected_type == 'number' and not isinstance(value, (int, float)):
                        return False, f"Le champ '{field}' doit être un nombre"
                    elif expected_type == 'boolean' and not isinstance(value, bool):
                        return False, f"Le champ '{field}' doit être un booléen"
            
            # Vérifier les valeurs énumérées
            enum_values = endpoint_config.get('enum_values', {})
            for field, values in enum_values.items():
                if field in request_data and request_data[field] not in values:
                    return False, f"La valeur '{request_data[field]}' n'est pas valide pour le champ '{field}'. Valeurs acceptées: {', '.join(values)}"
            
            return True, ""
        except Exception as e:
            return False, f"Erreur lors de la validation: {str(e)}"
    
    def send_request(self, request_data):
        """Envoie la requête à l'API en utilisant la méthode spécifiée dans le YAML."""
        try:
            endpoint_config = self.config.get('api', {}).get('endpoints', {}).get('lead_injection', {})
            if not endpoint_config:
                return {"status": "error", "message": "Configuration de l'endpoint 'lead_injection' non trouvée"}
            
            base_url = self.config.get('api', {}).get('base_url', '')
            path = endpoint_config.get('path', '').format(school_name='studi')
            method = endpoint_config.get('method', 'POST').upper()
            
            url = f"{base_url}{path}"
            print(url)
            # Utiliser la méthode HTTP spécifiée dans le YAML
            if method == 'GET':
                response = requests.get(url, params=request_data)
            elif method == 'POST':
                print(request_data)
                response = requests.post(url, json=request_data)
            elif method == 'PUT':
                response = requests.put(url, json=request_data)
            elif method == 'DELETE':
                response = requests.delete(url, json=request_data)
            elif method == 'PATCH':
                response = requests.patch(url, json=request_data)
            else:
                return {"status": "error", "message": f"Méthode HTTP non supportée: {method}"}
            
            return response
        except Exception as e:
            return {"status": "error", "message": str(e)} 