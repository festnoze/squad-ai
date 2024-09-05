class RagMethodDesc:
    def __init__(self, method_name, method_desc, method_params):
        self.method_name = method_name
        self.method_desc = method_desc 
        self.method_params = method_params

    def to_dict(self):
        return {
            'name': self.method_name,
            'description': self.method_desc,
            'parameters': self.method_params
        }