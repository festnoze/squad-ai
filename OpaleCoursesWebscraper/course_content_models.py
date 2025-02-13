class CourseContent:
    def __init__(self, parcours_id, parcours_code, name, is_demo, start_date, end_date,
                 inscription_start_date, inscription_end_date, promotion_name, promotion_id, is_planning_open):
        self.parcours_id = parcours_id
        self.parcours_code = parcours_code
        self.name = name
        self.is_demo = is_demo
        self.start_date = start_date
        self.end_date = end_date
        self.inscription_start_date = inscription_start_date
        self.inscription_end_date = inscription_end_date
        self.promotion_name = promotion_name
        self.promotion_id = promotion_id
        self.is_planning_open = is_planning_open

        self.matieres = []           # List of Matiere objects
        self.modules = []            # List of Module objects
        self.themes = []             # List of Theme objects
        self.ressources = []         # List of Ressource objects
        self.ressource_objects = []  # List of RessourceObject objects

    def add_matiere(self, matiere):
        self.matieres.append(matiere)

    def add_module(self, module):
        self.modules.append(module)

    def add_theme(self, theme):
        self.themes.append(theme)

    def add_ressource(self, ressource):
        self.ressources.append(ressource)

    def add_ressource_object(self, ro):
        self.ressource_objects.append(ro)

    def to_dict(self):
        return {
            'parcours_id': self.parcours_id,
            'parcours_code': self.parcours_code,
            'name': self.name,
            'is_demo': self.is_demo,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'inscription_start_date': self.inscription_start_date,
            'inscription_end_date': self.inscription_end_date,
            'promotion_name': self.promotion_name,
            'promotion_id': self.promotion_id,
            'is_planning_open': self.is_planning_open,
            'matieres': [m.to_dict() for m in self.matieres],
            'modules': [m.to_dict() for m in self.modules],
            'themes': [t.to_dict() for t in self.themes],
            'ressources': [r.to_dict() for r in self.ressources],
            'ressource_objects': [ro.to_dict() for ro in self.ressource_objects]
        }

    @staticmethod
    def from_dict(data):
        # Create the top-level CourseContent instance.
        course = CourseContent(
            parcours_id=data['parcours_id'],
            parcours_code=data['parcours_code'],
            name=data['name'],
            is_demo=data['is_demo'],
            start_date=data['start_date'],
            end_date=data['end_date'],
            inscription_start_date=data['inscription_start_date'],
            inscription_end_date=data['inscription_end_date'],
            promotion_name=data['promotion_name'],
            promotion_id=data['promotion_id'],
            is_planning_open=data['is_planning_open']
        )

        # --- Step 1: Create all objects without parent links.
        matiere_dict = {}
        for mdata in data.get('matieres', []):
            mat = Matiere.from_dict(mdata)
            matiere_dict[mat.matiere_id] = mat
            course.matieres.append(mat)

        module_dict = {}
        for mod_data in data.get('modules', []):
            mod = Module.from_dict(mod_data)
            module_dict[mod.module_id] = mod
            course.modules.append(mod)

        theme_dict = {}
        for tdata in data.get('themes', []):
            th = Theme.from_dict(tdata)
            theme_dict[th.theme_id] = th
            course.themes.append(th)

        ressource_dict = {}
        for rdata in data.get('ressources', []):
            r = Ressource.from_dict(rdata)
            ressource_dict[r.ressource_id] = r
            course.ressources.append(r)

        ressource_object_dict = {}
        for rodata in data.get('ressource_objects', []):
            ro = RessourceObject.from_dict(rodata)
            ressource_object_dict[ro.ressource_object_id] = ro
            course.ressource_objects.append(ro)

        # --- Step 2: Rebuild parent-child relationships using the stored IDs.
        # For Matiere, assign modules from the list of module IDs.
        for mdata in data.get('matieres', []):
            matiere = matiere_dict.get(mdata['matiere_id'])
            for mod_id in mdata.get('modules', []):
                mod = module_dict.get(mod_id)
                if mod:
                    mod.matiere = matiere
                    if mod not in matiere.modules:
                        matiere.modules.append(mod)

        # For Module, assign themes.
        for mod_data in data.get('modules', []):
            mod = module_dict.get(mod_data['module_id'])
            for theme_id in mod_data.get('themes', []):
                th = theme_dict.get(theme_id)
                if th:
                    th.module = mod
                    if th not in mod.themes:
                        mod.themes.append(th)

        # For Theme, assign ressources.
        for tdata in data.get('themes', []):
            th = theme_dict.get(tdata['theme_id'])
            for res_id in tdata.get('ressources', []):
                res = ressource_dict.get(res_id)
                if res:
                    res.theme = th
                    if res not in th.ressources:
                        th.ressources.append(res)

        # For Ressource, assign ressource_objects.
        for rdata in data.get('ressources', []):
            res = ressource_dict.get(rdata['ressource_id'])
            for ro_id in rdata.get('ressource_objects', []):
                ro = ressource_object_dict.get(ro_id)
                if ro:
                    ro.ressource = res
                    if ro not in res.ressource_objects:
                        res.ressource_objects.append(ro)

        # For each RessourceObject, update its hierarchy references.
        for rodata in data.get('ressource_objects', []):
            ro = ressource_object_dict.get(rodata['ressource_object_id'])
            if ro and ro.hierarchy:
                # In the serialized hierarchy we stored parent IDs.
                hierarchy_data = rodata.get('hierarchy', {})
                ro.hierarchy.set_parents(
                    ressource=ressource_dict.get(hierarchy_data.get('ressource_id')),
                    theme=theme_dict.get(hierarchy_data.get('theme_id')),
                    module=module_dict.get(hierarchy_data.get('module_id')),
                    matiere=matiere_dict.get(hierarchy_data.get('matiere_id'))
                )
        return course


class Matiere:
    def __init__(self, matiere_id, name, code):
        self.matiere_id = matiere_id
        self.name = name
        self.code = code
        self.modules = []  # List of Module objects

    def add_module(self, module):
        self.modules.append(module)

    def to_dict(self):
        return {
            'matiere_id': self.matiere_id,
            'name': self.name,
            'code': self.code,
            'modules': [module.module_id for module in self.modules]
        }

    @staticmethod
    def from_dict(data):
        return Matiere(
            matiere_id=data['matiere_id'],
            name=data['name'],
            code=data['code']
        )


class Module:
    def __init__(self, module_id, name, code, matiere=None):
        self.module_id = module_id
        self.name = name
        self.code = code
        self.matiere = matiere  # Reference to parent Matiere
        self.themes = []       # List of Theme objects

    def add_theme(self, theme):
        self.themes.append(theme)

    def to_dict(self):
        return {
            'module_id': self.module_id,
            'name': self.name,
            'code': self.code,
            'matiere_id': self.matiere.matiere_id if self.matiere else None,
            'themes': [theme.theme_id for theme in self.themes]
        }

    @staticmethod
    def from_dict(data):
        mod = Module(
            module_id=data['module_id'],
            name=data['name'],
            code=data['code'],
            matiere=None  # to be linked later
        )
        # Save the parent's ID temporarily.
        mod.matiere_id = data.get('matiere_id')
        return mod


class Theme:
    def __init__(self, theme_id, name, code, module=None):
        self.theme_id = theme_id
        self.name = name
        self.code = code
        self.module = module  # Reference to parent Module
        self.ressources = []  # List of Ressource objects

    def add_ressource(self, ressource):
        self.ressources.append(ressource)

    def to_dict(self):
        return {
            'theme_id': self.theme_id,
            'name': self.name,
            'code': self.code,
            'module_id': self.module.module_id if self.module else None,
            'ressources': [res.ressource_id for res in self.ressources]
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


class Ressource:
    def __init__(self, ressource_id, name, code, theme=None):
        self.ressource_id = ressource_id
        self.name = name
        self.code = code
        self.theme = theme  # Reference to parent Theme
        self.ressource_objects = []  # List of RessourceObject objects

    def add_ressource_object(self, ro):
        self.ressource_objects.append(ro)

    def to_dict(self):
        return {
            'ressource_id': self.ressource_id,
            'name': self.name,
            'code': self.code,
            'theme_id': self.theme.theme_id if self.theme else None,
            'ressource_objects': [ro.ressource_object_id for ro in self.ressource_objects]
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


class RessourceObject:
    def __init__(self, ressource_object_id, name, type, url):
        self.ressource_object_id = ressource_object_id
        self.name = name
        self.type = type
        self.url = url
        self.hierarchy = None  # Instance of RessourceObjectHierarchy
        self.ressource = None  # (Optional) Direct parent reference

    def set_hierarchy(self, hierarchy):
        self.hierarchy = hierarchy

    def to_dict(self):
        return {
            'ressource_object_id': self.ressource_object_id,
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
            url=data['url']
        )
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
            'ressource_id': self.ressource.ressource_id if self.ressource else None,
            'theme_id': self.theme.theme_id if self.theme else None,
            'module_id': self.module.module_id if self.module else None,
            'matiere_id': self.matiere.matiere_id if self.matiere else None
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
