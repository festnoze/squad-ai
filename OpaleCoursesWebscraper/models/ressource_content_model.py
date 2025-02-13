class Ressource:
    def __init__(self, ressource_id, name, code, theme=None):
        self.id = ressource_id
        self.name = name
        self.code = code
        self.theme = theme  # Reference to parent Theme
        self.ressource_objects = []  # List of RessourceObject objects

    def add_ressource_object(self, ro):
        self.ressource_objects.append(ro)

    def to_dict(self):
        return {
            'ressource_id': self.id,
            'name': self.name,
            'code': self.code,
            'theme_id': self.theme.id if self.theme else None,
            'ressource_objects': [ro.id for ro in self.ressource_objects]
        }

    @staticmethod
    def from_dict(data):
        res = Ressource(
            ressource_id=data['ressource_id'],
            name=data['name'],
            code=data['code'],
            theme=None  # to be linked later
        )
        res.theme_id = data.get('theme_id')
        return res