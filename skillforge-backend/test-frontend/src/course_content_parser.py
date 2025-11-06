import json
import os

from src.models.course_content import CourseContent
from src.models.matiere import Matiere
from src.models.module import Module
from src.models.ressource import Ressource
from src.models.ressource_object import RessourceObject, RessourceObjectHierarchy
from src.models.theme import Theme


class CourseContentParser:
    @staticmethod
    def analyse_parcours_file_composition(
        parcour_composition_filename: str,
        save_analysed_course: bool = True,
        load_analysed_course_instead_if_exist: bool = True,
    ) -> dict[str, CourseContent]:
        analysed_parcour_content_by_parcour_name: dict[str, CourseContent] = {}
        if "." not in parcour_composition_filename:
            parcour_composition_filename += ".json"

        with open("inputs/" + parcour_composition_filename, encoding="utf-8") as read_json_file:
            json_data = json.load(read_json_file)
            parcours_list = json_data.get("parcours", [])
            for parcour_data in parcours_list:
                if load_analysed_course_instead_if_exist and os.path.exists(
                    "outputs/" + parcour_data["name"] + ".json"
                ):
                    with open("outputs/" + parcour_data["name"] + ".json", encoding="utf-8") as read_json_file:
                        loaded_data = json.load(read_json_file)
                        course_content = CourseContent.from_dict(loaded_data)
                        analysed_parcour_content_by_parcour_name[parcour_data["name"]] = course_content
                        continue
                course_content = CourseContentParser.parse_parcour_content(parcour_data)
                analysed_parcour_content_by_parcour_name[parcour_data["name"]] = course_content
                if save_analysed_course:
                    serialized_data = course_content.to_dict(include_user_registration_infos=False)
                    with open("outputs/" + parcour_data["name"] + ".json", "w") as write_analysed_file:
                        json.dump(serialized_data, write_analysed_file, indent=4)

        return analysed_parcour_content_by_parcour_name

    @staticmethod
    def parse_parcour_content(parcours):
        course_content = CourseContent(
            parcours_id=parcours.get("parcoursId"),
            parcours_code=parcours.get("parcoursCode", ""),
            name=parcours.get("name", ""),
            is_demo=parcours.get("isDemo", False),
            start_date=parcours.get("startDate", ""),
            end_date=parcours.get("endDate", ""),
            inscription_start_date=parcours.get("inscriptionStartDate", ""),
            inscription_end_date=parcours.get("inscriptionEndDate", ""),
            promotion_name=parcours.get("promotionName", ""),
            promotion_id=parcours.get("promotionId"),
            is_planning_open=parcours.get("isPlanningOpen", False),
        )

        matieres_data = parcours.get("matieres", [])
        for matiere_data in matieres_data:
            # Parse Matiere
            matiere = Matiere(
                matiere_id=matiere_data.get("matiereId"),
                name=matiere_data.get("name", ""),
                code=matiere_data.get("code", ""),
            )
            course_content.add_matiere(matiere)

            modules_data = matiere_data.get("modules", [])
            for module_data in modules_data:
                # Parse Module
                module = Module(
                    module_id=module_data.get("moduleId"),
                    name=module_data.get("name", ""),
                    code=module_data.get("code", ""),
                    matiere=matiere,
                )
                matiere.add_module(module)
                course_content.add_module(module)

                themes_data = module_data.get("themes", [])
                for theme_data in themes_data:
                    # Parse Theme
                    theme = Theme(
                        theme_id=theme_data.get("themeId"),
                        name=theme_data.get("name", ""),
                        code=theme_data.get("code", ""),
                        module=module,
                    )
                    module.add_theme(theme)
                    course_content.add_theme(theme)

                    ressources_data = theme_data.get("ressources", [])
                    for ressource_data in ressources_data:
                        # Parse Ressource
                        ressource = Ressource(
                            ressource_id=ressource_data.get("ressourceId"),
                            name=ressource_data.get("name", ""),
                            code=ressource_data.get("code", ""),
                            theme=theme,
                        )
                        theme.add_ressource(ressource)
                        course_content.add_ressource(ressource)

                        ressource_objects_data = ressource_data.get("ressourceObjects", [])
                        for ro_data in ressource_objects_data:
                            # Parse RessourceObject
                            ro = RessourceObject(
                                ressource_object_id=ro_data.get("ressourceObjectId"),
                                name=ro_data.get("name", ""),
                                resource_type=ro_data.get("type", ""),
                                url=ro_data.get("url", ""),
                            )
                            # Create and set hierarchy
                            hierarchy = RessourceObjectHierarchy()
                            hierarchy.set_parents(ressource, theme, module, matiere)
                            ro.set_hierarchy(hierarchy)
                            ressource.add_ressource_object(ro)
                            course_content.add_ressource_object(ro)

        return course_content
