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
from datetime import timezone, timedelta, datetime
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)

class CalendarAgent:    
    def __init__(self):
        pass

    def set_user_info(self, first_name, last_name, email, owner_first_name, owner_last_name, owner_email, config_path: str = "calendar_agent.yaml"):
        """
        Initialize the Calendar Agent with user information and configuration.
        
        Args:
            first_name: Customer's first name
            last_name: Customer's last name
            email: Customer's email
            owner_first_name: Owner's (advisor) first name
            owner_last_name: Owner's (advisor) last name
            owner_email: Owner's (advisor) email
            config_path: Path to the calendar agent configuration file
        """
        logger.info(f"Initializing CalendarAgent for: {first_name} {last_name}")
        self.config = self._load_config(config_path)
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.owner_first_name = owner_first_name
        self.owner_last_name = owner_last_name
        self.owner_email = owner_email
        self.calendar_service = self._init_google_calendar()
        self.calendar_id = self.config["google_calendar"]["calendar_id"]

        self.duration = self.config["appointments"].get("duration_minutes", 30)
        self.max_slots = self.config["appointments"].get("max_slots", 3)
        
        self.tz_name = "Europe/Paris"
        self.tz = ZoneInfo(self.tz_name)
        self.tz_offset = timezone(timedelta(hours=2))  # Adaptable si besoin
        
        self.working_hours = self.config["appointments"]["working_hours"]
        self.days_ahead = self.config["appointments"].get("days_ahead", 2)

        self.available_slots = []
        self.date = ""
        self.slot_selected = ""

        # OpenAI configuration
        openai_config = self.config.get('openai', {})
        api_key = openai_config.get('api_key', os.getenv("OPENAI_API_KEY", ""))
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=api_key)
        
        self.model = openai_config.get('model', 'gpt-4-turbo')
        self.temperature = openai_config.get('temperature', 0.1)
        self.max_tokens = openai_config.get('max_tokens', 500)

    def _load_config(self, path):
        """Load YAML configuration from the specified path."""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            full_path = os.path.join(project_root, path)
            logger.debug(f"Loading calendar agent config from: {full_path}")
            with open(full_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading config from {path}: {e}")
            raise

    def _init_google_calendar(self):
        """Initialize Google Calendar service."""
        try:
            credentials_path = self.config["google_calendar"]["credentials_path"]
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            full_path = os.path.join(project_root, credentials_path)
            
            credentials = service_account.Credentials.from_service_account_file(
                full_path,
                scopes=["https://www.googleapis.com/auth/calendar"]
            )
            
            service = build("calendar", "v3", credentials=credentials)
            logger.info("Google Calendar service initialized successfully")
            return service
        except Exception as e:
            logger.error(f"Error initializing Google Calendar service: {e}", exc_info=True)
            raise

    def analyze_text_for_calendar_inquiry(self, text):
        """
        Analyze user input text to identify scheduling requests and handle the appointment booking flow.
        
        Args:
            text: The user's input text
        
        Returns:
            str: Response message to the user
        """
        logger.info(f"Analyzing text for calendar operations: {text[:50]}...")
        
        try:
            # If we already have available slots, check if the user is selecting one
            if self.available_slots:
                return self._handle_time_slot_selection(text)
            else:
                # Otherwise, extract date/time preferences and find available slots
                return self._handle_date_extraction(text)
        except Exception as e:
            logger.error(f"Error analyzing text: {e}", exc_info=True)
            return "Je rencontre un problème pour gérer votre demande de rendez-vous. Pourriez-vous réessayer avec une autre date ou contacter directement un conseiller?"

    def _handle_date_extraction(self, text):
        """Extract date and time preferences from text and find available slots."""
        try:
            # Extract date/time information from user input using LLM
            date_info = self._extract_date_info(text)
            
            if not date_info.get("date"):
                return "Pourriez-vous me préciser quel jour vous conviendrait pour un rendez-vous? Par exemple, demain, lundi prochain, le 15 juin, etc."
            
            # Convert extracted date to actual datetime
            date_str = date_info["date"]
            preferred_time = date_info.get("time_preference", "morning")
            
            try:
                target_date = self._parse_date(date_str)
            except:
                return f"Je n'ai pas bien compris la date '{date_str}'. Pourriez-vous reformuler avec une date précise comme 'demain', 'lundi prochain' ou '15 juin'?"
            
            # Find available slots
            self.date = target_date
            available_slots = self._find_available_slots(target_date, preferred_time)
            
            if not available_slots:
                # Try the next day if no slots available
                next_day = target_date + timedelta(days=1)
                available_slots = self._find_available_slots(next_day, preferred_time)
                if not available_slots:
                    return f"Désolé, aucun créneau n'est disponible le {target_date.strftime('%d/%m/%Y')} ni le jour suivant. Pourriez-vous proposer une autre date?"
                else:
                    self.date = next_day
                    target_date = next_day
            
            self.available_slots = available_slots
            
            # Format slots for display
            slots_formatted = "\n".join([f"{i+1}. {slot.strftime('%H:%M')}" for i, slot in enumerate(available_slots[:self.max_slots])])
            
            return f"Voici les créneaux disponibles le {target_date.strftime('%d/%m/%Y')} :\n{slots_formatted}\nQuel créneau vous conviendrait? (répondez avec le numéro)"
            
        except Exception as e:
            logger.error(f"Error extracting date information: {e}", exc_info=True)
            return "Je n'ai pas pu déterminer vos disponibilités. Pourriez-vous indiquer une date spécifique pour le rendez-vous?"

    def _handle_time_slot_selection(self, text):
        """Handle the user's selection of a time slot."""
        try:
            # Try to extract a slot number from the user's response
            slot_number = self._extract_slot_number(text)
            
            if not slot_number or slot_number < 1 or slot_number > len(self.available_slots):
                return f"Pourriez-vous choisir un numéro de créneau entre 1 et {len(self.available_slots)}?"
            
            selected_slot = self.available_slots[slot_number - 1]
            self.slot_selected = selected_slot
            
            # Create the appointment
            created = self._create_appointment(selected_slot)
            
            if created:
                formatted_date = selected_slot.strftime('%d/%m/%Y à %H:%M')
                return f"Parfait! J'ai réservé un rendez-vous pour vous le {formatted_date} avec {self.owner_first_name} {self.owner_last_name}. Vous recevrez une confirmation par email. Merci et à bientôt!"
            else:
                return "Je n'ai pas pu créer le rendez-vous. Veuillez réessayer ou contacter directement un conseiller."
                
        except Exception as e:
            logger.error(f"Error handling slot selection: {e}", exc_info=True)
            return "Je n'ai pas pu traiter votre sélection. Pourriez-vous réessayer en indiquant simplement le numéro du créneau?"

    def _extract_date_info(self, text):
        """Extract date and time preference information from text using OpenAI."""
        try:
            prompt = f"""
            Extrait la date et la préférence horaire du message suivant:
            
            "{text}"
            
            Réponds sous format JSON avec les champs:
            - date: la date mentionnée (format: DD/MM/YYYY ou expression comme "demain", "lundi prochain", etc.)
            - time_preference: la période préférée (matin, après-midi, soir, ou spécifique comme 14h)
            
            Si aucune date n'est mentionnée, renvoie une date vide.
            Si aucune préférence d'heure n'est mentionnée, renvoie "morning" par défaut.
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Tu es un assistant qui extrait des informations de rendez-vous."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            logger.info(f"Extracted date info: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error extracting date info: {e}", exc_info=True)
            return {"date": "", "time_preference": "morning"}

    def _extract_slot_number(self, text):
        """Extract the slot number from user input."""
        try:
            prompt = f"""
            L'utilisateur répond à une liste de créneaux numérotés (de 1 à {self.max_slots}).
            Extrait uniquement le numéro du créneau choisi de ce message:
            
            "{text}"
            
            Réponds seulement avec le numéro entier, sans autre texte.
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Tu es un assistant qui extrait un numéro de sélection."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=10
            )
            
            result = response.choices[0].message.content.strip()
            try:
                return int(result)
            except:
                return None
            
        except Exception as e:
            logger.error(f"Error extracting slot number: {e}", exc_info=True)
            return None

    def _parse_date(self, date_str):
        """Parse a date string into a datetime object."""
        try:
            # First attempt: Try direct parsing for common formats
            try:
                return parser.parse(date_str, dayfirst=True).replace(tzinfo=self.tz)
            except:
                pass
            
            # Second attempt: Use LLM to convert relative date expression to an absolute date
            prompt = f"""
            Convertis l'expression de date suivante en date absolue (format DD/MM/YYYY):
            
            "{date_str}"
            
            Aujourd'hui nous sommes le {datetime.now().strftime('%d/%m/%Y')}.
            Réponds uniquement avec la date au format DD/MM/YYYY, sans autre texte.
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Tu es un assistant qui convertit des expressions de date en dates absolues."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=20
            )
            
            result = response.choices[0].message.content.strip()
            return datetime.strptime(result, "%d/%m/%Y").replace(tzinfo=self.tz)
            
        except Exception as e:
            logger.error(f"Error parsing date: {e}", exc_info=True)
            raise ValueError(f"Unable to parse date: {date_str}")

    def _find_available_slots(self, target_date, preferred_time="morning"):
        """Find available time slots for the given date."""
        try:
            # Get the day of week (0=Monday, 6=Sunday)
            day_of_week = target_date.weekday()
            
            # Check if this is a working day
            if day_of_week >= 5:  # Weekend
                return []
            
            # Get working hours for this day
            day_hours = self.working_hours.get(str(day_of_week), {"start": "09:00", "end": "17:00"})
            
            # Parse working hours
            start_hour, start_min = map(int, day_hours["start"].split(":"))
            end_hour, end_min = map(int, day_hours["end"].split(":"))
            
            # Adjust based on preferred time
            if preferred_time == "morning":
                end_hour = min(end_hour, 12)
            elif preferred_time == "afternoon":
                start_hour = max(start_hour, 12)
                end_hour = min(end_hour, 17)
            elif preferred_time == "evening":
                start_hour = max(start_hour, 17)
            
            # Create datetime objects for start and end of working hours
            day_start = target_date.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
            day_end = target_date.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
            
            # Generate potential slots
            slots = []
            current = day_start
            while current + timedelta(minutes=self.duration) <= day_end:
                slots.append(current)
                current += timedelta(minutes=30)  # 30-minute intervals
            
            # Filter out booked slots
            available_slots = self._filter_booked_slots(slots, target_date)
            
            return available_slots
            
        except Exception as e:
            logger.error(f"Error finding available slots: {e}", exc_info=True)
            return []

    def _filter_booked_slots(self, slots, target_date):
        """Filter out already booked slots from the potential slots."""
        try:
            # Get events for the day
            day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            events_result = self.calendar_service.events().list(
                calendarId=self.calendar_id,
                timeMin=day_start.isoformat(),
                timeMax=day_end.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Create list of busy periods
            busy_periods = []
            for event in events:
                start = parser.parse(event['start'].get('dateTime', event['start'].get('date')))
                end = parser.parse(event['end'].get('dateTime', event['end'].get('date')))
                busy_periods.append((start, end))
            
            # Filter out slots that overlap with busy periods
            available_slots = []
            for slot in slots:
                slot_end = slot + timedelta(minutes=self.duration)
                is_available = True
                
                for busy_start, busy_end in busy_periods:
                    # Check if slot overlaps with busy period
                    if (slot < busy_end and slot_end > busy_start):
                        is_available = False
                        break
                
                if is_available:
                    available_slots.append(slot)
            
            return available_slots
            
        except Exception as e:
            logger.error(f"Error filtering booked slots: {e}", exc_info=True)
            return slots  # Return all slots if there's an error

    def _create_appointment(self, slot):
        """Create a calendar appointment for the selected slot."""
        try:
            end_time = slot + timedelta(minutes=self.duration)
            
            event = {
                'summary': f'RDV {self.first_name} {self.last_name}',
                'location': 'Appel téléphonique',
                'description': f'Rendez-vous avec {self.first_name} {self.last_name} ({self.email})',
                'start': {
                    'dateTime': slot.isoformat(),
                    'timeZone': self.tz_name,
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': self.tz_name,
                },
                'attendees': [
                    {'email': self.email, 'displayName': f'{self.first_name} {self.last_name}'},
                    {'email': self.owner_email, 'displayName': f'{self.owner_first_name} {self.owner_last_name}'}
                ],
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 60},
                        {'method': 'popup', 'minutes': 15},
                    ],
                },
                'sendUpdates': 'all'
            }
            
            event = self.calendar_service.events().insert(
                calendarId=self.calendar_id,
                body=event,
                sendUpdates='all'
            ).execute()
            
            logger.info(f"Event created: {event.get('htmlLink')}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating appointment: {e}", exc_info=True)
            return False
