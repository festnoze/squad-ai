from pydantic import BaseModel, Field


class RessourceObjectRequest(BaseModel):
    """Request model for a resource object to be scraped.

    Attributes:
        ressource_object_id: ID of the resource object
        name: Name of the resource
        type: Type of resource ('opale' or 'pdf')
        url: URL of the resource to scrape (optional - will be skipped if not provided)
    """

    ressource_object_id: str | int = Field(..., description="ID of the resource object")
    name: str = Field(..., description="Name of the resource")
    type: str = Field(..., description="Type of resource (opale, pdf)")
    url: str | None = Field(None, description="URL of the resource to scrape (optional)")


class RessourceRequest(BaseModel):
    """Request model for a ressource.

    Attributes:
        ressource_id: ID of the ressource
        name: Name of the ressource
        code: Code of the ressource
        ressource_objects: List of IDs of resource objects
    """

    ressource_id: str | int = Field(..., description="ID of the ressource")
    name: str = Field(..., description="Name of the ressource")
    code: str = Field(..., description="Code of the ressource")
    ressource_objects: list[str | int] = Field(default_factory=list, description="List of resource object IDs")


class ThemeRequest(BaseModel):
    """Request model for a theme.

    Attributes:
        theme_id: ID of the theme
        name: Name of the theme
        code: Code of the theme
        ressources: List of IDs of ressources
    """

    theme_id: str | int = Field(..., description="ID of the theme")
    name: str = Field(..., description="Name of the theme")
    code: str = Field(..., description="Code of the theme")
    ressources: list[str | int] = Field(default_factory=list, description="List of ressource IDs")


class ModuleRequest(BaseModel):
    """Request model for a module.

    Attributes:
        module_id: ID of the module
        name: Name of the module
        code: Code of the module
        themes: List of IDs of themes
    """

    module_id: str | int = Field(..., description="ID of the module")
    name: str = Field(..., description="Name of the module")
    code: str = Field(..., description="Code of the module")
    themes: list[str | int] = Field(default_factory=list, description="List of theme IDs")


class MatiereRequest(BaseModel):
    """Request model for a matiere.

    Attributes:
        matiere_id: ID of the matiere
        name: Name of the matiere
        code: Code of the matiere
        modules: List of IDs of modules
    """

    matiere_id: str | int = Field(..., description="ID of the matiere")
    name: str = Field(..., description="Name of the matiere")
    code: str = Field(..., description="Code of the matiere")
    modules: list[str | int] = Field(default_factory=list, description="List of module IDs")


class CourseContentScrapingRequest(BaseModel):
    """Request model for scraping course content.

    Attributes:
        parcours_id: ID of the parcours/course
        parcours_code: Code of the parcours/course
        name: Name of the parcours/course
        is_demo: Whether this is a demo parcours
        start_date: Start date of the parcours (optional)
        end_date: End date of the parcours (optional)
        inscription_start_date: Inscription start date (optional)
        inscription_end_date: Inscription end date (optional)
        promotion_name: Name of the promotion (optional)
        promotion_id: ID of the promotion (optional)
        is_planning_open: Whether planning is open (optional)
        matieres: List of matieres
        modules: List of modules
        themes: List of themes
        ressources: List of ressources
        ressource_objects: List of resource objects to scrape
    """

    parcours_id: str | int = Field(..., description="ID of the parcours/course")
    parcours_code: str = Field(..., description="Code of the parcours/course")
    name: str = Field(..., description="Name of the parcours/course")
    is_demo: bool = Field(..., description="Whether this is a demo parcours")
    start_date: str | None = Field(None, description="Start date of the parcours")
    end_date: str | None = Field(None, description="End date of the parcours")
    inscription_start_date: str | None = Field(None, description="Inscription start date")
    inscription_end_date: str | None = Field(None, description="Inscription end date")
    promotion_name: str | None = Field(None, description="Name of the promotion")
    promotion_id: str | int | None = Field(None, description="ID of the promotion")
    is_planning_open: bool | None = Field(None, description="Whether planning is open")
    matieres: list[MatiereRequest] = Field(default_factory=list, description="List of matieres")
    modules: list[ModuleRequest] = Field(default_factory=list, description="List of modules")
    themes: list[ThemeRequest] = Field(default_factory=list, description="List of themes")
    ressources: list[RessourceRequest] = Field(default_factory=list, description="List of ressources")
    ressource_objects: list[RessourceObjectRequest] = Field(default_factory=list, description="List of resources to scrape")

    def build_enriched_context_metadata(self, ressource_object: RessourceObjectRequest, pdf_url: str | None, scraping_status: str = "success", scraping_error: str | None = None) -> dict:
        """Build enriched context metadata for a resource object.

        Traverses the hierarchical structure to find parent entities and builds
        comprehensive metadata for database storage.

        Args:
            ressource_object: The resource object being scraped
            pdf_url: URL of extracted PDF (for opale courses)
            scraping_status: Status of scraping operation ("success" or "failed")
            scraping_error: Error message if scraping failed

        Returns:
            Dictionary with enriched context metadata including hierarchical structure
        """
        # Find parent ressource
        ressource_entity = self._find_ressource_by_object_id(ressource_object.ressource_object_id)

        # Find parent theme
        theme_entity = self._find_theme_by_ressource_id(ressource_entity.ressource_id) if ressource_entity else None

        # Find parent module
        module_entity = self._find_module_by_theme_id(theme_entity.theme_id) if theme_entity else None

        # Find parent matiere
        matiere_entity = self._find_matiere_by_module_id(module_entity.module_id) if module_entity else None

        # Build breadcrumb navigation path
        breadcrumb_parts = [self.name]
        if matiere_entity:
            breadcrumb_parts.append(matiere_entity.name)
        if module_entity:
            breadcrumb_parts.append(module_entity.name)
        if theme_entity:
            breadcrumb_parts.append(theme_entity.name)
        if ressource_entity:
            breadcrumb_parts.append(ressource_entity.name)
        breadcrumb_parts.append(ressource_object.name)

        # Build base metadata with parcours info
        metadata: dict = {
            "parcours": {
                "parcours_id": str(self.parcours_id),
                "parcours_code": self.parcours_code,
                "parcours_name": self.name,
                "is_demo": self.is_demo,
            },
            "breadcrumb": " > ".join(breadcrumb_parts),
        }

        # Add matiere if found
        if matiere_entity:
            metadata["matiere"] = {
                "matiere_id": str(matiere_entity.matiere_id),
                "matiere_code": matiere_entity.code,
                "matiere_name": matiere_entity.name,
            }

        # Add module if found
        if module_entity:
            metadata["module"] = {
                "module_id": str(module_entity.module_id),
                "module_code": module_entity.code,
                "module_name": module_entity.name,
            }

        # Add theme if found
        if theme_entity:
            metadata["theme"] = {
                "theme_id": str(theme_entity.theme_id),
                "theme_code": theme_entity.code,
                "theme_name": theme_entity.name,
            }

        # Add ressource if found
        if ressource_entity:
            metadata["ressource"] = {
                "ressource_id": str(ressource_entity.ressource_id),
                "ressource_code": ressource_entity.code,
                "ressource_name": ressource_entity.name,
            }

        # Add ressource_object (current content)
        metadata["ressource_object"] = {
            "ressource_object_id": str(ressource_object.ressource_object_id),
            "ressource_object_name": ressource_object.name,
            "ressource_object_type": ressource_object.type,
            "ressource_object_url": ressource_object.url,
        }

        # Add media metadata
        metadata["media"] = {
            "pdf_url": pdf_url,
            "has_pdf": bool(pdf_url),
            "has_interactive": ressource_object.type == "opale",
        }

        # Add scraping status
        metadata["scraping_status"] = scraping_status
        if scraping_error:
            metadata["scraping_error"] = scraping_error

        return metadata

    def _find_ressource_by_object_id(self, ressource_object_id: str | int) -> RessourceRequest | None:
        """Find ressource that contains the given ressource_object_id."""
        ressource_object_id_str = str(ressource_object_id)
        for ressource in self.ressources:
            if ressource_object_id_str in [str(ro_id) for ro_id in ressource.ressource_objects]:
                return ressource
        return None

    def _find_theme_by_ressource_id(self, ressource_id: str | int) -> ThemeRequest | None:
        """Find theme that contains the given ressource_id."""
        ressource_id_str = str(ressource_id)
        for theme in self.themes:
            if ressource_id_str in [str(r_id) for r_id in theme.ressources]:
                return theme
        return None

    def _find_module_by_theme_id(self, theme_id: str | int) -> ModuleRequest | None:
        """Find module that contains the given theme_id."""
        theme_id_str = str(theme_id)
        for module in self.modules:
            if theme_id_str in [str(t_id) for t_id in module.themes]:
                return module
        return None

    def _find_matiere_by_module_id(self, module_id: str | int) -> MatiereRequest | None:
        """Find matiere that contains the given module_id."""
        module_id_str = str(module_id)
        for matiere in self.matieres:
            if module_id_str in [str(m_id) for m_id in matiere.modules]:
                return matiere
        return None
