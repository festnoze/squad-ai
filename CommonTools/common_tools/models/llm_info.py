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

    @staticmethod
    def factory_from_dict(llm_dict:dict, llms_temp:float = None, llm_api_key:str = None ) -> 'LlmInfo':
        model = llm_dict['model']
        llms_temp = llms_temp if llms_temp else llm_dict['temperature'] if 'temperature' in llm_dict else 0.5
        timeout = llm_dict['timeout'] if 'timeout' in llm_dict else 60
        is_chat_model = llm_dict['is_chat_model'] if 'is_chat_model' in llm_dict else True
        is_reasoning_model = llm_dict['is_reasoning_model'] if 'is_reasoning_model' in llm_dict else False
        inference_provider_name = None
        
        if ' ' in llm_dict['type']:
            llm_type_str = llm_dict['type'].split(' ')[0]
            inference_provider_name = llm_dict['type'].split(' ')[1]
            llm_type_enum = LangChainAdapterType[llm_type_str]
            llm_type_enum.set_default_inference_provider_name(inference_provider_name)
        else:
            llm_type_str = llm_dict['type']
            llm_type_enum = LangChainAdapterType[llm_type_str]

        llm_info = LlmInfo(
                        type=llm_type_enum, 
                        model=model, 
                        timeout=timeout, 
                        temperature=llms_temp,
                        is_chat_model=is_chat_model,
                        is_reasoning_model=is_reasoning_model,
                        api_key=llm_api_key
                    )
        return llm_info
    
    def __str__(self):
        return f"LlmInfo(type='{self.type}', model='{self.model}', timeout='{self.timeout}', temperature='{str(self.temperature)}', is_chat_model='{str(self.is_chat_model)}', api_key='{self.api_key[:5]+'*****' if self.api_key else 'Not provided'}')"