from enum import Enum

class LangChainAdapterType(Enum):
    OpenAI = "OpenAI"
    Ollama = "Ollama"
    Google = "Google"
    Anthropic = "Anthropic"
    Groq = "Groq"
    InferenceProvider = "InferenceProvider"

    def __init__(self, value: str = None):
        self._value_ = value  # Set the enum value

    @property
    def default_inference_provider_name(self):
        """
        Getter for the default inference provider name.
        """
        return self.__class__._default_inference_provider_name

    @classmethod
    def set_default_inference_provider_name(cls, name: str):
        """
        Setter for the default inference provider name.
        """
        cls._default_inference_provider_name = name

    @classmethod
    def get_default_inference_provider_name(cls):
        """
        Class-level getter for the default inference provider name.
        """
        return cls._default_inference_provider_name
    
