class Matiere:
    def __init__(self, matiere_id, name, code):
        self.id = matiere_id
        self.name = name
        self.code = code
        self.modules = []  # List of Module objects

    def add_module(self, module):
        self.modules.append(module)

    def to_dict(self):
        return {
            'matiere_id': self.id,
            'name': self.name,
            'code': self.code,
            'modules': [module.id for module in self.modules]
        }

    @staticmethod
    def from_dict(data):
        return Matiere(
            matiere_id=data['matiere_id'],
            name=data['name'],
            code=data['code']
        )