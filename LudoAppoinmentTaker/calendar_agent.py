import json
import yaml
import os
import requests
from openai import OpenAI
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dateutil import parser
from googleapiclient.errors import HttpError
from datetime import timezone,timedelta,datetime
from zoneinfo import ZoneInfo



class CalendarAgent:
    
    def __init__(self,first_name,last_name,email,owner_first_name,owner_last_name,owner_email,config_path: str = "calendar_agent.yaml"):
        self.config = self._load_config(config_path)
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.owner_first_name = owner_first_name
        self.owner_last_name = owner_last_name
        self.owner_email = owner_email
        self.calendar_service = self._init_google_calendar()
        self.calendar_id = self.config["google_calendar"]["calendar_id"]

        self.duration = self.config["rendez_vous"].get("duration_minutes", 30)
        self.max_slots = self.config["rendez_vous"].get("max_slots", 3)
        
        self.tz_name = "Europe/Paris"
        self.tz = ZoneInfo(self.tz_name)
        self.tz_offset = timezone(timedelta(hours=2))  # Adaptable si besoin
        
        self.working_hours = self.config["rendez_vous"]["working_hours"]
        self.days_ahead = self.config["rendez_vous"].get("days_ahead", 2)

        self.available_slots = []
        self.date = ""
        self.slot_selected = ""

        openai_config = self.config.get('openai', {})
        api_key = openai_config.get('api_key', '')
        
        # Initialiser le client OpenAI avec la version 1.12.0
        self.client = OpenAI(api_key=api_key)
        
        self.model = openai_config.get('model', 'gpt-4-turbo')
        self.temperature = openai_config.get('temperature', 0.1)
        self.max_tokens = openai_config.get('max_tokens', 500)


    def _load_config(self, path):
        with open(path, "r") as f:
            return yaml.safe_load(f)


    def _init_google_calendar(self):
        creds = service_account.Credentials.from_service_account_file(
            self.config["google_calendar"]["credentials_path"],
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        return build("calendar", "v3", credentials=creds)

    # Fonction pour récupérer les événements existants
    def get_events(self, date, time_begin, time_end):
        """
        Utilise freebusy pour récupérer les créneaux occupés d'un agenda partagé.
        """
         # Conversion en datetime avec timezone explicite
        start = datetime.combine(date, datetime.strptime(time_begin, "%H:%M").time()).replace(tzinfo=self.tz)
        end = datetime.combine(date, datetime.strptime(time_end, "%H:%M").time()).replace(tzinfo=self.tz)

        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "timeZone": self.tz_name,
            "items": [{"id": self.calendar_id}]
        }
        print(body)
        response = self.calendar_service.freebusy().query(body=body).execute()
        busy_times = response['calendars'][self.calendar_id]['busy']
        return busy_times

    def formater_creneau(self,creneau):

        mois_fr = [
            "janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"
        ]
        # Parse les datetime ISO avec fuseau horaire
        start_dt = datetime.fromisoformat(creneau['start'])
        end_dt = datetime.fromisoformat(creneau['end'])

        # Mise en forme en français
        jour = start_dt.day
        mois = mois_fr[start_dt.month - 1]
        heure_debut = start_dt.strftime("%-H heure")
        minute_debut = start_dt.strftime("%M")
        heure_fin = end_dt.strftime("%-H heure")
        minute_fin = end_dt.strftime("%M")

        # Gestion du "à 9 heure" vs "à 9 heure 30"
        if minute_fin == "00":
            fin_str = f"{heure_fin}"
        else:
            fin_str = f"{heure_fin} {minute_fin}"

        if minute_debut == "00":
            debut_str = f"{heure_debut}"
        else:
            debut_str = f"{heure_debut} {minute_debut}"

        return f"Le {jour} {mois} de {debut_str} à {fin_str}"

    def formater_date(self,date_str):

        mois_fr = [
            "janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"
        ]
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        jour = date_obj.day
        mois = mois_fr[date_obj.month - 1]
        return f"{jour} {mois}"

    def analyze_text(self,text):
        # Utilise OpenAI pour poser la question via Twilio/WS en dehors de cette classe
        if self.date == "":
            extracted_info = self._extract_info_with_llm(text)
            available_slots = self._get_available_time_slots(extracted_info["date"], extracted_info["time_begin"], extracted_info["time_end"],self.duration,self.max_slots)
    
            if len(available_slots) == 0:
                self.available_slots = []
                self.date = ""
                return f"""
                Malheureusement je ne vois aucun créneau disponible le {self.formater_date(extracted_info["date"])} 
                entre {extracted_info["time_begin"]} et {extracted_info["time_end"]}.
                Peux tu me donner un autre jour et moment de la journée ?
                """
            else:
                self.date = extracted_info["date"]
                self.available_slots = available_slots
                slots_str = ""
                for i,slot in enumerate(available_slots):
                    slots_str += self.formater_creneau(slot) + ", "
                return f"""Voici les créneaux disponibles : {slots_str}.
                Lequel de ces créneaux peux convenir ?
                """
        else:
            self.slot_selected  = self._extract_slot_with_llm(text)
            if self.slot_selected != "":
                self.create_event(self.slot_selected)
                return f"""
                Merci beaucoup pour votre choix.
                Un rendez-vous a été posé {self.formater_creneau(self.slot_selected)} avec {self.owner_first_name} 
                et une invitation vous a été envoyée.
                Passez une excellente journée. A bientôt chez Studi.
                """
            else:
                slots_str = ""
                for i,slot in enumerate(self.available_slots):
                    slots_str += self.formater_creneau(slot) + ", "
                return f"""
                Je n'ai pas compris le créneau que tu m'as indiqué.
                Voici les créneaux disponibles : {slots_str}
                """

    def create_event(self,slot):
        # Détails de l’événement
        event = {
            'summary': 'Rendez-vous Studi avec '+self.first_name+' '+self.last_name,
            'location': 'En ligne',
            'description': 'Un rendez-vous avec un client.',
            'start': {
                'dateTime': self.slot_selected['start'],
                'timeZone': self.tz_name,
            },
            'end': {
                'dateTime': self.slot_selected['end'],
                'timeZone': self.tz_name,
            },
            #'attendees': [
             #   {'email': self.email},  # <- ajoute ici l'adresse de l'invité
            #],
            'reminders': {
                'useDefault': True,
            },
        }
        print("event",event)
        event_response = self.calendar_service.events().insert(calendarId=self.calendar_id, body=event, sendUpdates='all').execute()
        print(event_response)

    def _extract_info_with_llm(self, text):
        """Extrait les informations du texte en utilisant un LLM."""
        
        try:
            
            # Construire le prompt
            prompt ="""Tu es un assistant qui transforme des expressions temporelles naturelles en un format structuré.

                    Quand je t’envoie un texte qui parle d’un moment dans la semaine ou dans la journée (ex : "mardi prochain le matin", "demain après-midi", "ce soir"), tu dois me répondre avec un objet JSON au format suivant :

                    {
                    "date": "YYYY-MM-DD",
                    "time_begin": "HH:MM",
                    "time_end": "HH:MM"
                    }

                    Considère que :
                    - "matin" → 09:00 à 12:00
                    - "après-midi" → 13:00 à 17:00
                    - "soir" → 18:00 à 21:00
                    - "nuit" → 22:00 à 06:00 le lendemain

                    La date actuelle est : 2025-04-18 (un vendredi)

                    Réponds uniquement avec le JSON.
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
            print(extracted_info)
            return extracted_info
            
            
        except Exception as e:
            print(f"Erreur lors de l'extraction avec le LLM: {str(e)}")
            return {}

    def _extract_slot_with_llm(self, text):
        """Extrait le créneau du texte en utilisant un LLM."""
            
        # Construire le prompt
        prompt =f"""
        Tu es un assistant intelligent qui aide à choisir un créneau horaire de rendez-vous.

        Voici la liste des créneaux proposés :
        {json.dumps(self.available_slots, indent=2)}

        L'utilisateur répond oralement ou par écrit, par exemple :
        - Le deuxième
        - Celui de 11h30
        - Le créneau de 9h

        Ta tâche est de retrouver le créneau le plus proche de ce qu’il demande et de retourner le dictionnaire exact correspondant.

        Réponds uniquement par le bon dictionnaire correspondant.
        Réponds uniquement avec le JSON.
        Si tu ne trouves pas le créneau, réponds avec une chaine vide.
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
        print("response",response_text)
        # Nettoyer la réponse pour s'assurer qu'elle est un JSON valide
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        
        # Parser le JSON
        extracted_info = json.loads(response_text)
        
        return extracted_info


    def _get_available_time_slots(self,date, time_begin, time_end, duration_minutes=30, max_slots=3):
        """
        Retourne les premiers créneaux disponibles de `duration_minutes` dans l’agenda donné.
        """
        date = datetime.strptime(date, "%Y-%m-%d").date()
        events = self.get_events( date, time_begin, time_end)
        
        start_time = datetime.combine(date, datetime.strptime(time_begin, "%H:%M").time()).replace(tzinfo=self.tz_offset)
        end_time = datetime.combine(date, datetime.strptime(time_end, "%H:%M").time()).replace(tzinfo=self.tz_offset)

        slots = []
        current = start_time

        while current + timedelta(minutes=duration_minutes) <= end_time:
            slot_start = current
            slot_end = current + timedelta(minutes=duration_minutes)

            # Vérifie les conflits avec les créneaux occupés
            overlap = False
            for event in events:
                busy_start = datetime.fromisoformat(event['start']).astimezone(self.tz_offset)
                busy_end = datetime.fromisoformat(event['end']).astimezone(self.tz_offset)

                if slot_start < busy_end and slot_end > busy_start:
                    overlap = True
                    break

            if not overlap:
                slots.append({
                    "start": slot_start.isoformat(),
                    "end": slot_end.isoformat()
                })

                if len(slots) >= max_slots:
                    break

            current += timedelta(minutes=duration_minutes)  # créneaux glissants
        print("slots",slots)
        return slots
