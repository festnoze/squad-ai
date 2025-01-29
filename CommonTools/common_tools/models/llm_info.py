from common_tools.models.langchain_adapter_type import LangChainAdapterType

class LlmInfo:
    def __init__(self, type:LangChainAdapterType, model:str, timeout:int, temperature:float, is_chat_model:bool = True, is_reasoning_model:bool = False, api_key:str = None):
        self.type = type
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.is_chat_model = is_chat_model
        self.api_key = api_key
        self.is_reasoning_model = is_reasoning_model
        self.inference_provider_name = type.default_inference_provider_name if type == LangChainAdapterType.InferenceProvider else None

    def __str__(self):
        return f"LlmInfo(type='{self.type}', model='{self.model}', timeout='{self.timeout}', temperature='{str(self.temperature)}', is_chat_model='{str(self.is_chat_model)}', api_key='{self.api_key[:5]+'*****' if self.api_key else 'Not provided'}')"