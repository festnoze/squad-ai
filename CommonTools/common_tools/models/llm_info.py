class LlmInfo:
    def __init__(self, type, model, timeout, temperature, api_key = None):
        self.type = type
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.api_key = api_key

    def __str__(self):
        return f"LlmInfo(type='{self.type}', model='{self.model}', timeout='{self.timeout}', temperature='{str(self.temperature)}', api_key='{self.api_key[:5]+'*****' if self.api_key else 'Not provided'}')"