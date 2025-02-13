class RessourceObject:
    def __init__(self, ressource_object_id, name, type, url, ressource=None):
        self.id = ressource_object_id
        self.name = name
        self.type = type
        self.url = url
        self.hierarchy = None

    def set_hierarchy(self, hierarchy):
        self.hierarchy = hierarchy

    def to_dict(self):
        return {
            'ressource_object_id': self.id,
            'name': self.name,
            'type': self.type,
            'url': self.url,
            'hierarchy': self.hierarchy.to_dict() if self.hierarchy else None
        }

    @staticmethod
    def from_dict(data):
        ro = RessourceObject(
            ressource_object_id=data['ressource_object_id'],
            name=data['name'],
            type=data['type'],
            url=data['url'],
        )
        ro.ressource_id = data.get('ressource_id')
        if data.get('hierarchy'):
            ro.hierarchy = RessourceObjectHierarchy.from_dict(data['hierarchy'])
        return ro


class RessourceObjectHierarchy:
    def __init__(self):
        # Only keep parent object references.
        self.ressource = None
        self.theme = None
        self.module = None
        self.matiere = None

    def set_parents(self, ressource, theme, module, matiere):
        self.ressource = ressource
        self.theme = theme
        self.module = module
        self.matiere = matiere

    def to_dict(self):
        return {
            'ressource_id': self.ressource.id if self.ressource else None,
            'theme_id': self.theme.id if self.theme else None,
            'module_id': self.module.id if self.module else None,
            'matiere_id': self.matiere.id if self.matiere else None,
        }

    @staticmethod
    def from_dict(data):
        hierarchy = RessourceObjectHierarchy()
        # Temporarily store parent IDs for later linking.
        hierarchy.ressource_id = data.get('ressource_id')
        hierarchy.theme_id = data.get('theme_id')
        hierarchy.module_id = data.get('module_id')
        hierarchy.matiere_id = data.get('matiere_id')
        return hierarchy
