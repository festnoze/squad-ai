"""Course loader utility for loading course content from JSON files."""

import json
from pathlib import Path

from src.config import Config
from src.models.course_content import CourseContent


class CourseLoader:
    """Utility class for loading and managing course content."""

    @staticmethod
    def load_available_courses(outputs_dir: Path | None = None) -> list[str]:
        """Load list of available courses from outputs directory.

        Args:
            outputs_dir: Path to outputs directory (defaults to Config.OUTPUTS_DIR)

        Returns:
            List of course names
        """
        if outputs_dir is None:
            outputs_dir = Config.OUTPUTS_DIR

        if not outputs_dir.exists():
            return []

        courses = []
        for file_path in outputs_dir.glob("*.json"):
            # Extract course name from filename
            # Format: "<course_name>.json"
            course_name = file_path.stem
            courses.append(course_name)

        return sorted(courses)

    @staticmethod
    def load_course_structure(course_name: str, outputs_dir: Path | None = None) -> CourseContent:
        """Load course structure from JSON file.

        Args:
            course_name: Name of the course to load
            outputs_dir: Path to outputs directory (defaults to Config.OUTPUTS_DIR)

        Returns:
            CourseContent object with full hierarchy

        Raises:
            FileNotFoundError: If course file doesn't exist
            json.JSONDecodeError: If JSON file is invalid
        """
        if outputs_dir is None:
            outputs_dir = Config.OUTPUTS_DIR

        # Construct file path
        file_path = outputs_dir / f"{course_name}.json"

        if not file_path.exists():
            msg = f"Course file not found: {file_path}"
            raise FileNotFoundError(msg)

        # Load and parse JSON
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        # Create CourseContent object from dict
        return CourseContent.from_dict(data)

    @staticmethod
    def get_matieres(course: CourseContent) -> list:
        """Get all matieres from a course.

        Args:
            course: CourseContent object

        Returns:
            List of Matiere objects
        """
        return course.matieres

    @staticmethod
    def get_modules(matiere) -> list:
        """Get all modules from a matiere.

        Args:
            matiere: Matiere object

        Returns:
            List of Module objects
        """
        return matiere.modules if matiere else []

    @staticmethod
    def get_themes(module) -> list:
        """Get all themes from a module.

        Args:
            module: Module object

        Returns:
            List of Theme objects
        """
        return module.themes if module else []

    @staticmethod
    def get_ressources(theme) -> list:
        """Get all ressources from a theme.

        Args:
            theme: Theme object

        Returns:
            List of Ressource objects
        """
        return theme.ressources if theme else []

    @staticmethod
    def get_ressource_objects(ressource) -> list:
        """Get all ressource objects from a ressource.

        Args:
            ressource: Ressource object

        Returns:
            List of RessourceObject objects
        """
        return ressource.ressource_objects if ressource else []
