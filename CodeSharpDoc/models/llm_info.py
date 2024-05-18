class LlmInfo:
    def __init__(self, type, model, timeout, api_key):
        self.type = type
        self.model = model
        self.timeout = timeout
        self.api_key = api_key

    def __str__(self):
        return f"LlmInfo(type='{self.type}', model='{self.model}', timeout='{self.timeout}', api_key='{self.api_key}')"