from models.course_content_models import CourseContent
from models.matiere_content_model import Matiere
from models.module_content_model import Module
from models.theme_content_model import Theme
from models.ressource_content_model import Ressource
from models.ressource_object_content_model import RessourceObject, RessourceObjectHierarchy

class CourseContentParser:

    @staticmethod
    def parse_course_content(course_data):
        parcours_list = course_data.get('parcours', [])
        parcours = parcours_list[0]

        course_content = CourseContent(
            parcours_id=parcours.get('parcoursId'),
            parcours_code=parcours.get('parcoursCode', ''),
            name=parcours.get('name', ''),
            is_demo=parcours.get('isDemo', False),
            start_date=parcours.get('startDate', ''),
            end_date=parcours.get('endDate', ''),
            inscription_start_date=parcours.get('inscriptionStartDate', ''),
            inscription_end_date=parcours.get('inscriptionEndDate', ''),
            promotion_name=parcours.get('promotionName', ''),
            promotion_id=parcours.get('promotionId'),
            is_planning_open=parcours.get('isPlanningOpen', False)
        )

        matieres_data = parcours.get('matieres', [])
        for matiere_data in matieres_data:
            # Parse Matiere
            matiere = Matiere(
                matiere_id=matiere_data.get('matiereId'),
                name=matiere_data.get('name', ''),
                code=matiere_data.get('code', '')
            )
            course_content.add_matiere(matiere)

            modules_data = matiere_data.get('modules', [])
            for module_data in modules_data:
                # Parse Module
                module = Module(
                    module_id=module_data.get('moduleId'),
                    name=module_data.get('name', ''),
                    code=module_data.get('code', ''),
                    matiere=matiere
                )
                matiere.add_module(module)
                course_content.add_module(module)

                themes_data = module_data.get('themes', [])
                for theme_data in themes_data:
                    # Parse Theme
                    theme = Theme(
                        theme_id=theme_data.get('themeId'),
                        name=theme_data.get('name', ''),
                        code=theme_data.get('code', ''),
                        module=module
                    )
                    module.add_theme(theme)
                    course_content.add_theme(theme)

                    ressources_data = theme_data.get('ressources', [])
                    for ressource_data in ressources_data:
                        # Parse Ressource
                        ressource = Ressource(
                            ressource_id=ressource_data.get('ressourceId'),
                            name=ressource_data.get('name', ''),
                            code=ressource_data.get('code', ''),
                            theme=theme
                        )
                        theme.add_ressource(ressource)
                        course_content.add_ressource(ressource)

                        ressource_objects_data = ressource_data.get('ressourceObjects', [])
                        for ro_data in ressource_objects_data:
                            # Parse RessourceObject
                            ro = RessourceObject(
                                ressource_object_id=ro_data.get('ressourceObjectId'),
                                name=ro_data.get('name', ''),
                                type=ro_data.get('type', ''),
                                url=ro_data.get('url', '')
                            )
                            # Create and set hierarchy
                            hierarchy = RessourceObjectHierarchy()
                            hierarchy.set_parents(ressource, theme, module, matiere)
                            ro.set_hierarchy(hierarchy)
                            ressource.add_ressource_object(ro)
                            course_content.add_ressource_object(ro)

        return course_content
