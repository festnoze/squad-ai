"""CourseContent model - root of the course hierarchy."""

from src.models.matiere import Matiere
from src.models.module import Module
from src.models.ressource import Ressource
from src.models.ressource_object import RessourceObject
from src.models.theme import Theme


class CourseContent:
    """Represents the complete course content with hierarchical structure."""

    def __init__(
        self,
        parcours_id: str,
        parcours_code: str,
        name: str,
        is_demo: bool,
        start_date: str | None = None,
        end_date: str | None = None,
        inscription_start_date: str | None = None,
        inscription_end_date: str | None = None,
        promotion_name: str | None = None,
        promotion_id: str | None = None,
        is_planning_open: bool | None = None,
    ) -> None:
        """Initialize a CourseContent instance.

        Args:
            parcours_id: Unique identifier for the course
            parcours_code: Course code/reference
            name: Display name of the course
            is_demo: Whether this is a demo course
            start_date: Course start date (optional)
            end_date: Course end date (optional)
            inscription_start_date: Registration start date (optional)
            inscription_end_date: Registration end date (optional)
            promotion_name: Promotion/cohort name (optional)
            promotion_id: Promotion/cohort ID (optional)
            is_planning_open: Whether planning is open (optional)
        """
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

        self.matieres: list[Matiere] = []
        self.modules: list[Module] = []
        self.themes: list[Theme] = []
        self.ressources: list[Ressource] = []
        self.ressource_objects: list[RessourceObject] = []

    def add_matiere(self, matiere: Matiere) -> None:
        """Add a matiere if not already present."""
        if matiere and matiere.id and not any(m.id == matiere.id for m in self.matieres):
            self.matieres.append(matiere)

    def add_module(self, module: Module) -> None:
        """Add a module if not already present."""
        if module and module.id and not any(m.id == module.id for m in self.modules):
            self.modules.append(module)

    def add_theme(self, theme: Theme) -> None:
        """Add a theme if not already present."""
        if theme and theme.id and not any(t.id == theme.id for t in self.themes):
            self.themes.append(theme)

    def add_ressource(self, ressource: Ressource) -> None:
        """Add a ressource if not already present."""
        if ressource and ressource.id and not any(r.id == ressource.id for r in self.ressources):
            self.ressources.append(ressource)

    def add_ressource_object(self, ro: RessourceObject) -> None:
        """Add a ressource object if not already present."""
        if ro and ro.id and not any(r.id == ro.id for r in self.ressource_objects):
            self.ressource_objects.append(ro)

    def to_dict(self, include_user_registration_infos: bool = True) -> dict:
        """Convert to dictionary for serialization."""
        result: dict = {
            "parcours_id": self.parcours_id,
            "parcours_code": self.parcours_code,
            "name": self.name,
            "is_demo": self.is_demo,
            "matieres": [m.to_dict() for m in self.matieres],
            "modules": [m.to_dict() for m in self.modules],
            "themes": [t.to_dict() for t in self.themes],
            "ressources": [r.to_dict() for r in self.ressources],
            "ressource_objects": [ro.to_dict() for ro in self.ressource_objects],
        }

        if include_user_registration_infos:
            result.update({
                "start_date": self.start_date,
                "end_date": self.end_date,
                "inscription_start_date": self.inscription_start_date,
                "inscription_end_date": self.inscription_end_date,
                "promotion_name": self.promotion_name,
                "promotion_id": self.promotion_id,
                "is_planning_open": self.is_planning_open,
            })
        return result

    @staticmethod
    def from_dict(data: dict):
        """Create CourseContent from dictionary with full hierarchy reconstruction."""
        # Create the top-level CourseContent instance.
        course = CourseContent(
            parcours_id=data["parcours_id"],
            parcours_code=data["parcours_code"],
            name=data["name"],
            is_demo=data["is_demo"],
            # User registration infos (optional)
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            inscription_start_date=data.get("inscription_start_date"),
            inscription_end_date=data.get("inscription_end_date"),
            promotion_name=data.get("promotion_name"),
            promotion_id=data.get("promotion_id"),
            is_planning_open=data.get("is_planning_open"),
        )

        # --- Step 1: Create all objects without parent nor children relationships.
        all_matieres_dict = {}
        for mdata in data.get("matieres", []):
            mat = Matiere.from_dict(mdata)
            all_matieres_dict[mat.id] = mat
            course.matieres.append(mat)

        all_modules_dict = {}
        for mod_data in data.get("modules", []):
            mod = Module.from_dict(mod_data)
            all_modules_dict[mod.id] = mod
            course.modules.append(mod)

        all_themes_dict = {}
        for tdata in data.get("themes", []):
            th = Theme.from_dict(tdata)
            all_themes_dict[th.id] = th
            course.themes.append(th)

        all_ressources_dict = {}
        for rdata in data.get("ressources", []):
            r = Ressource.from_dict(rdata)
            all_ressources_dict[r.id] = r
            course.ressources.append(r)

        all_ressources_object_dict = {}
        for rodata in data.get("ressource_objects", []):
            ro = RessourceObject.from_dict(rodata)
            all_ressources_object_dict[ro.id] = ro
            course.ressource_objects.append(ro)

        # --- Step 2: Rebuild parent-child relationships using the stored IDs.

        # For Matiere, assign modules from the list of module IDs.
        for mdata in data.get("matieres", []):
            matiere = all_matieres_dict.get(mdata["matiere_id"])
            for mod_id in mdata.get("modules", []):
                mod = all_modules_dict.get(mod_id)
                if mod:
                    mod.matiere = matiere  # Assign parent
                    if mod not in matiere.modules:
                        matiere.modules.append(mod)  # Assign children

        # For Module, assign themes.
        for mod_data in data.get("modules", []):
            mod = all_modules_dict.get(mod_data["module_id"])
            for theme_id in mod_data.get("themes", []):
                th = all_themes_dict.get(theme_id)
                if th:
                    th.module = mod  # Assign parent
                    if th not in mod.themes:
                        mod.themes.append(th)  # Assign children

        # For Theme, assign ressources.
        for tdata in data.get("themes", []):
            th = all_themes_dict.get(tdata["theme_id"])
            for res_id in tdata.get("ressources", []):
                res = all_ressources_dict.get(res_id)
                if res:
                    res.theme = th  # Assign parent
                    if res not in th.ressources:
                        th.ressources.append(res)  # Assign children

        # For Ressource, assign ressource_objects.
        for rdata in data.get("ressources", []):
            res = all_ressources_dict.get(rdata["ressource_id"])
            for ro_id in rdata.get("ressource_objects", []):
                ro = all_ressources_object_dict.get(ro_id)
                if ro:
                    ro.ressource = res  # Assign parent
                    if ro not in res.ressource_objects:
                        res.ressource_objects.append(ro)  # Assign children

        # For each RessourceObject, update its hierarchy references.
        for rodata in data.get("ressource_objects", []):
            ro = all_ressources_object_dict.get(rodata["ressource_object_id"])
            if ro and ro.hierarchy:
                # In the serialized hierarchy we stored parent IDs.
                hierarchy_data = rodata.get("hierarchy", {})
                ro.hierarchy.set_parents(
                    ressource=all_ressources_dict.get(hierarchy_data.get("ressource_id")),
                    theme=all_themes_dict.get(hierarchy_data.get("theme_id")),
                    module=all_modules_dict.get(hierarchy_data.get("module_id")),
                    matiere=all_matieres_dict.get(hierarchy_data.get("matiere_id")),
                )
        return course
