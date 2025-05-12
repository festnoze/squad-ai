import json
import yaml
import os
import requests
from openai import OpenAI
import logging

logger = logging.getLogger(__name__)

class LeadAgent:
    def __init__(self, config_path="lid_api_config.yaml"):
        """Initialize lead agent with YAML configuration."""
        try:
            # Adjust to handle paths relative to project root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            full_path = os.path.join(project_root, config_path)
            
            with open(full_path, 'r') as file:
                self.config = yaml.safe_load(file)
            
            # Verify configuration structure
            if not self.config or 'api' not in self.config or 'endpoints' not in self.config['api']:
                raise ValueError("YAML configuration must contain an 'api.endpoints' section")
            
            if 'lead_injection' not in self.config['api']['endpoints']:
                raise ValueError("YAML configuration must contain a 'lead_injection' endpoint")
            
            # Initialize OpenAI client
            openai_key = os.getenv("OPENAI_API_KEY", "")
            self.client = OpenAI(api_key=openai_key)
            
            self.extracted_info = {}
            self.missing_fields = []
            self.request_data = []
            
        except FileNotFoundError:
            error_msg = f"Initialize lead agent error: Configuration file {config_path} does not exist"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        except yaml.YAMLError as e:
            error_msg = f"Initialize lead agent error: Error in YAML file format: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Initialize lead agent error: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def analyze_text(self, text):
        """Analyze text and extract relevant information."""
        logger.info(f"Analyzing text: {text[:50]}...")
        try:
            # Extract information with LLM
            new_extracted_info = self._extract_info_with_llm(text)
            logger.debug(f"Extracted info: {new_extracted_info}")
            
            # Merge with previously extracted information
            self.extracted_info = {**self.extracted_info, **new_extracted_info}
            
            # Identify missing fields
            missing_fields = self._get_missing_fields(self.extracted_info)
            
            # Format request with default values
            request_data = self._format_request(self.extracted_info)
        
            # Validate request
            is_valid, error_message = self._validate_request(request_data)
            logger.info(f"Request validation - Valid: {is_valid}, Error: {error_message}")
            
            if not is_valid:
                # Format missing fields for user-friendly message
                missing_desc = []
                for field in missing_fields:
                    missing_desc.append(field["description"])
                
                if missing_desc:
                    return f"Merci pour ces informations. Pourriez-vous me préciser {', '.join(missing_desc)} s'il vous plaît ?"
                else:
                    return f"Je n'ai pas pu valider vos informations : {error_message}. Pourriez-vous les vérifier ?"
            
            # Send the request if valid
            try:
                api_response = self.send_request(request_data)
                
                if 200 <= api_response.status_code < 300:
                    return "Merci pour vos informations. J'ai bien enregistré votre demande. Un conseiller vous contactera très prochainement. Avez-vous d'autres questions?"
                else:
                    logger.error(f"API error: {api_response.status_code} - {api_response.text}")
                    return "Désolé, une erreur est survenue lors de l'enregistrement de vos informations. Pouvez-vous réessayer dans quelques instants?"
            
            except Exception as e:
                logger.error(f"Error sending request: {e}", exc_info=True)
                return "Une erreur technique est survenue. Veuillez réessayer plus tard."
            
        except Exception as e:
            logger.error(f"Error in analyze_text: {e}", exc_info=True)
            return "Je n'ai pas pu analyser correctement vos informations. Pourriez-vous les reformuler?"
    
    def _extract_info_with_llm(self, text):
        """Extract information from text using OpenAI."""
        try:
            model = "gpt-4-turbo"
            prompt = f"""
            Extrait les informations suivantes du texte de l'utilisateur suivant:
            
            ```
            {text}
            ```
            
            - prénom
            - nom
            - email
            - téléphone (format français)
            - Formation ou domaine d'intérêt (si mentionné)
            
            Réponds uniquement au format JSON avec les clés : firstName, lastName, email, phone, trainingInterest.
            Si une information n'est pas présente, laisse le champ vide.
            """
            
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Tu es un assistant spécialisé dans l'extraction d'informations de contact."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Clean phone number if present
            if result.get('phone'):
                result['phone'] = self._clean_phone_number(result['phone'])
                
            return result
            
        except Exception as e:
            logger.error(f"Error extracting info with LLM: {e}", exc_info=True)
            return {}
    
    def _clean_phone_number(self, phone):
        """Clean and format phone number."""
        try:
            # Remove any non-digit characters
            cleaned = ''.join(filter(str.isdigit, phone))
            
            # Handle country code
            if cleaned.startswith('33') and len(cleaned) > 9:
                cleaned = '0' + cleaned[2:]
            elif cleaned.startswith('330') and len(cleaned) > 10:
                cleaned = cleaned[3:]
            elif not cleaned.startswith('0') and len(cleaned) == 9:
                cleaned = '0' + cleaned
                
            # Format with spaces if desired
            if len(cleaned) == 10:
                formatted = ' '.join([cleaned[0:2], cleaned[2:4], cleaned[4:6], cleaned[6:8], cleaned[8:10]])
                return formatted
                
            return cleaned
            
        except Exception as e:
            logger.error(f"Error cleaning phone number: {e}")
            return phone
    
    def _get_missing_fields(self, info):
        """Identify missing required fields."""
        missing = []
        
        # Define required fields with descriptions
        required_fields = [
            {"field": "firstName", "description": "votre prénom"},
            {"field": "lastName", "description": "votre nom"},
            {"field": "email", "description": "votre adresse email"},
            {"field": "phone", "description": "votre numéro de téléphone"}
        ]
        
        # Check for empty or missing fields
        for field in required_fields:
            if field["field"] not in info or not info[field["field"]]:
                missing.append(field)
                
        return missing
    
    def _format_request(self, info):
        """Format request data with extracted information."""
        # Get endpoint configuration
        endpoint_config = self.config["api"]["endpoints"]["lead_injection"]
        request_structure = endpoint_config.get("request_structure", {})
        
        # Start with default values if any
        formatted_data = request_structure.get("default_values", {}).copy()
        
        # Map extracted info to API fields using the mapping
        field_mapping = request_structure.get("field_mapping", {})
        
        for api_field, source_field in field_mapping.items():
            # If source field is in extracted info, use it
            if source_field in info and info[source_field]:
                # Handle nested fields (using dot notation)
                if "." in api_field:
                    parts = api_field.split(".")
                    curr = formatted_data
                    for part in parts[:-1]:
                        if part not in curr:
                            curr[part] = {}
                        curr = curr[part]
                    curr[parts[-1]] = info[source_field]
                else:
                    formatted_data[api_field] = info[source_field]
        
        return formatted_data
    
    def _validate_request(self, data):
        """Validate the request data."""
        # Get validation rules
        endpoint_config = self.config["api"]["endpoints"]["lead_injection"]
        required_fields = endpoint_config.get("validation", {}).get("required_fields", [])
        
        # Check required fields
        for field_path in required_fields:
            # Handle nested fields (using dot notation)
            if "." in field_path:
                parts = field_path.split(".")
                curr = data
                for part in parts:
                    if not curr or part not in curr:
                        return False, f"Champ requis manquant: {field_path}"
                    curr = curr[part]
                
                if not curr:  # Empty value
                    return False, f"Champ requis vide: {field_path}"
            else:
                if field_path not in data or not data[field_path]:
                    return False, f"Champ requis manquant: {field_path}"
        
        # Add additional validation rules here if needed
        # For example, email format, phone number format, etc.
        
        return True, ""
    
    def send_request(self, data):
        """Send request to the API."""
        try:
            # Get API configuration
            endpoint_config = self.config["api"]["endpoints"]["lead_injection"]
            url = endpoint_config["url"]
            method = endpoint_config.get("method", "POST")
            headers = endpoint_config.get("headers", {})
            
            # Send request
            logger.info(f"Sending {method} request to {url}")
            logger.debug(f"Request data: {data}")
            
            if method.upper() == "POST":
                response = requests.post(url, json=data, headers=headers)
            elif method.upper() == "PUT":
                response = requests.put(url, json=data, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            logger.info(f"API response: {response.status_code}")
            logger.debug(f"Response content: {response.text[:200]}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error sending request: {e}", exc_info=True)
            raise
