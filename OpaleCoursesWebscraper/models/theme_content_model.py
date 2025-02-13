class Theme:
    def __init__(self, theme_id, name, code, module=None):
        self.id = theme_id
        self.name = name
        self.code = code
        self.module = module  # Reference to parent Module
        self.ressources = []  # List of Ressource objects

    def add_ressource(self, ressource):
        self.ressources.append(ressource)

    def to_dict(self):
        return {
            'theme_id': self.id,
            'name': self.name,
            'code': self.code,
            'module_id': self.module.id if self.module else None,
            'ressources': [res.id for res in self.ressources]
        }

    @staticmethod
    def from_dict(data):
        th = Theme(
            theme_id=data['theme_id'],
            name=data['name'],
            code=data['code'],
            module=None  # to be linked later
        )
        th.module_id = data.get('module_id')
        return th