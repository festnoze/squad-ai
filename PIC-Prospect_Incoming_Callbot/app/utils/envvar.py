# /!\ 'load_dotenv()'  Must be done beforehand in the main script!
import os
from dotenv import load_dotenv

class EnvHelper:
    is_env_loaded = False

    @staticmethod
    def get_openai_api_key() -> str:
        return EnvHelper.get_env_variable_value_by_name('OPENAI_API_KEY')
    
    @staticmethod
    def get_salesforce_username() -> str:
        return EnvHelper.get_env_variable_value_by_name('SALESFORCE_USERNAME')

    @staticmethod
    def get_salesforce_password() -> str:
        return EnvHelper.get_env_variable_value_by_name('SALESFORCE_PASSWORD')

    @staticmethod
    def get_salesforce_client_secret() -> str:
        return EnvHelper.get_env_variable_value_by_name('SALESFORCE_CLIENT_SECRET')

    @staticmethod
    def get_rag_api_host() -> str:
        return EnvHelper.get_env_variable_value_by_name('RAG_API_HOST')

    @staticmethod
    def get_rag_api_port() -> int:
        port_str = EnvHelper.get_env_variable_value_by_name('RAG_API_PORT')
        return int(port_str)
    
    @staticmethod
    def get_rag_api_is_ssh() -> bool:
        value = EnvHelper.get_env_variable_value_by_name('RAG_API_IS_SSH')
        return value.lower() == 'true'

    @staticmethod
    def get_do_audio_preprocessing() -> bool:
        value = EnvHelper.get_env_variable_value_by_name('DO_AUDIO_PREPROCESSING')
        return value.lower() == 'true'
    
    @staticmethod
    def get_keep_audio_files() -> bool:        
        value = EnvHelper.get_env_variable_value_by_name('KEEP_AUDIO_FILES')
        return value.lower() == 'true'

    @staticmethod
    def get_text_to_speech_provider() -> str:
        return EnvHelper.get_env_variable_value_by_name('TEXT_TO_SPEECH_PROVIDER')

    @staticmethod
    def get_text_to_speech_voice() -> str:
        return EnvHelper.get_env_variable_value_by_name('TEXT_TO_SPEECH_VOICE')

    @staticmethod
    def get_text_to_speech_instructions() -> str:
        return EnvHelper.get_env_variable_value_by_name('TEXT_TO_SPEECH_INSTRUCTIONS')

    @staticmethod
    def get_text_to_speech_model() -> str:
        return EnvHelper.get_env_variable_value_by_name('TEXT_TO_SPEECH_MODEL')

    @staticmethod
    def get_speech_to_text_provider() -> str:
        return EnvHelper.get_env_variable_value_by_name('SPEECH_TO_TEXT_PROVIDER')

    @staticmethod
    def get_can_speech_be_interupted() -> bool:
        value = EnvHelper.get_env_variable_value_by_name('CAN_SPEECH_BE_INTERUPTED')
        return value.lower() == 'true'
    
    @staticmethod
    def get_twilio_sid() -> str:
        return EnvHelper.get_env_variable_value_by_name('TWILIO_SID')

    @staticmethod
    def get_twilio_auth() -> str:
        return EnvHelper.get_env_variable_value_by_name('TWILIO_AUTH')

    @staticmethod
    def get_repeat_user_input() -> bool:
        value = EnvHelper.get_env_variable_value_by_name('REPEAT_USER_INPUT')
        return value.lower() == 'true'

    @staticmethod
    def get_test_audio() -> bool:
        value = EnvHelper.get_env_variable_value_by_name('TEST_AUDIO', fails_if_missing=False)
        return value and value.lower() == 'true'

    @staticmethod
    def get_test_call_count() -> int:
        value = EnvHelper.get_env_variable_value_by_name('TEST_CALL_COUNT', fails_if_missing=False)
        return int(value) if value else 1

    @staticmethod
    def get_available_actions() -> list[str]:
        actions : list[str] = EnvHelper.get_env_variable_value_by_name('AVAILABLE_ACTIONS', fails_if_missing=False)
        return [action.strip() for action in actions.split(',')] if actions else []

    @staticmethod
    def get_waiting_music_on_calendar() -> bool:
        value = EnvHelper.get_env_variable_value_by_name('WAITING_MUSIC_ON_CALENDAR', fails_if_missing=False)
        return value and value.lower() == 'true'

    @staticmethod
    def get_waiting_music_on_rag() -> bool:
        value = EnvHelper.get_env_variable_value_by_name('WAITING_MUSIC_ON_RAG', fails_if_missing=False)
        return value and value.lower() == 'true'

    @staticmethod
    def get_waiting_music_increasing_volume_duration() -> float:
        value = EnvHelper.get_env_variable_value_by_name('WAITING_MUSIC_INCREASING_VOLUME_DURATION', fails_if_missing=False)
        return float(value) if value else 0.0

    @staticmethod
    def get_waiting_music_start_delay() -> float:
        value = EnvHelper.get_env_variable_value_by_name('WAITING_MUSIC_START_DELAY', fails_if_missing=False)
        return float(value) if value else 0.0

    @staticmethod
    def get_background_noise_enabled() -> bool:
        value = EnvHelper.get_env_variable_value_by_name('BACKGROUND_NOISE_ENABLED', fails_if_missing=False)
        return value and value.lower() == 'true'

    @staticmethod
    def get_background_noise_volume() -> float:
        value = EnvHelper.get_env_variable_value_by_name('BACKGROUND_NOISE_VOLUME', fails_if_missing=False)
        return float(value) if value else 0.1

    @staticmethod
    def get_speech_threshold() -> int:
        value = EnvHelper.get_env_variable_value_by_name('SPEECH_THRESHOLD', fails_if_missing=False)
        return int(value) if value else 950

    @staticmethod
    def get_required_silence_ms_to_answer() -> int:
        value = EnvHelper.get_env_variable_value_by_name('REQUIRED_SILENCE_MS_TO_ANSWER', fails_if_missing=False)
        return int(value) if value else 700

    @staticmethod
    def get_min_audio_bytes_for_processing() -> int:
        value = EnvHelper.get_env_variable_value_by_name('MIN_AUDIO_BYTES_FOR_PROCESSING', fails_if_missing=False)
        return int(value) if value else 1000

    @staticmethod
    def get_max_audio_bytes_for_processing() -> int:
        value = EnvHelper.get_env_variable_value_by_name('MAX_AUDIO_BYTES_FOR_PROCESSING', fails_if_missing=False)
        return int(value) if value else 200000

    @staticmethod
    def get_max_silence_duration_before_reasking() -> int:
        value = EnvHelper.get_env_variable_value_by_name('MAX_SILENCE_DURATION_BEFORE_REASKING', fails_if_missing=False)
        return int(value) if value else 15000

    @staticmethod
    def get_max_silence_duration_before_hangup() -> int:
        value = EnvHelper.get_env_variable_value_by_name('MAX_SILENCE_DURATION_BEFORE_HANGUP', fails_if_missing=False)
        return int(value) if value else 70000

    @staticmethod
    def get_speak_anew_on_long_silence() -> bool:
        value = EnvHelper.get_env_variable_value_by_name('SPEAK_ANEW_ON_LONG_SILENCE', fails_if_missing=False)
        return value and value.lower() == 'true'
    
    @staticmethod
    def get_google_credentials_filepath() -> str:
        return EnvHelper.get_env_variable_value_by_name('GOOGLE_CREDENTIALS_FILEPATH')
    
    @staticmethod
    def get_do_acknowledge_user_speech() -> bool:
        value = EnvHelper.get_env_variable_value_by_name('DO_ACKNOWLEDGE_USER_SPEECH', fails_if_missing=False)
        return value and value.lower() == 'true'
    
    @staticmethod
    def get_long_acknowledgement() -> bool:
        value = EnvHelper.get_env_variable_value_by_name('LONG_ACKNOWLEDGEMENT', fails_if_missing=False)
        return value and value.lower() == 'true'

    @staticmethod
    def get_conversation_persistence_type() -> str:
        return EnvHelper.get_env_variable_value_by_name('CONVERSATION_PERSISTENCE_TYPE', fails_if_missing=False) or 'no'
    
    ### Internal methods###
    #######################

    @staticmethod
    def _get_custom_env_files() -> str:
        return EnvHelper.get_env_variable_value_by_name('CUSTOM_ENV_FILES', load_env=False, fails_if_missing=False)
    
    @staticmethod
    def _get_llms_json() -> str:
        return EnvHelper.get_env_variable_value_by_name('LLMS_JSON')  
    
    @staticmethod
    def _init_load_env():
        if not EnvHelper.is_env_loaded:
            load_dotenv()
            EnvHelper._load_custom_env_files()
            EnvHelper.is_env_loaded = True

    @staticmethod
    def _load_custom_env_files():
        custom_env_files = EnvHelper._get_custom_env_files()
        
        # In case no custom additionnal env. files are defined into a 'CUSTOM_ENV_FILES' key of the '.env' file 
        if not custom_env_files:
            return 
        
        custom_env_filenames = [filename.strip() for filename in custom_env_files.split(',')]
        for custom_env_filename in custom_env_filenames:
            if not os.path.exists(custom_env_filename):
                raise FileNotFoundError(f"/!\\ Environment file: '{custom_env_filename}' was not found at the project root.")
            load_dotenv(custom_env_filename)
    
    @staticmethod
    def get_env_variable_value_by_name(variable_name: str, load_env: bool = True, fails_if_missing: bool = True, remove_comments: bool = True) -> str:
        if variable_name not in os.environ:
            if load_env:
                EnvHelper._init_load_env()
            variable_value: str = os.getenv(variable_name, None)
            if not variable_value:
                if fails_if_missing:
                    raise ValueError(f'Variable named: "{variable_name}" is not set in the environment')
                else:
                    return None
            os.environ[variable_name] = variable_value
        
        value = os.environ[variable_name]
        if remove_comments and '#' in value:
            value = value.split('#')[0].strip()
        
        return value
    
    def _get_llm_env_variables(skip_commented_lines:bool = True):
        return file.get_as_yaml('.llm.env.yaml', skip_commented_lines)
    