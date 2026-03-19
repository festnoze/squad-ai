"""Validation de l'arborescence source avant génération."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CategoryInfo:
    """Informations sur une catégorie détectée (supporte l'imbrication)."""

    name: str
    path: Path
    mp3_files: list[Path] = field(default_factory=list)
    subcategories: list[CategoryInfo] = field(default_factory=list)

    @property
    def total_stories(self) -> int:
        """Nombre total d'histoires dans cette catégorie et ses sous-catégories."""
        count = len(self.mp3_files)
        for sub in self.subcategories:
            count += sub.total_stories
        return count


@dataclass
class ValidationReport:
    """Rapport de validation de l'arborescence source."""

    valid: bool
    categories: list[CategoryInfo] = field(default_factory=list)
    total_stories: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def validate_source(source_dir: Path) -> ValidationReport:
    """Valide l'arborescence source récursivement et retourne un rapport structuré."""
    report = ValidationReport(valid=True)

    if not source_dir.exists():
        report.valid = False
        report.errors.append(f"Le dossier source n'existe pas : {source_dir}")
        return report

    if not source_dir.is_dir():
        report.valid = False
        report.errors.append(f"Le chemin source n'est pas un dossier : {source_dir}")
        return report

    # Lister les sous-dossiers
    subdirs = sorted(
        [d for d in source_dir.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )

    if not subdirs:
        # Pas de sous-dossiers — vérifier s'il y a au moins des MP3 au niveau racine
        mp3_files = sorted(
            [f for f in source_dir.iterdir() if f.is_file() and f.suffix.lower() == ".mp3"],
            key=lambda f: f.name,
        )
        if not mp3_files:
            report.valid = False
            report.errors.append(
                f"Aucune catégorie (sous-dossier) ni fichier .mp3 trouvé dans : {source_dir}"
            )
        return report

    for subdir in subdirs:
        category = _validate_directory(subdir, report)
        if category is not None:
            report.categories.append(category)
            report.total_stories += category.total_stories

    return report


def _validate_directory(directory: Path, report: ValidationReport) -> CategoryInfo | None:
    """Valide récursivement un dossier et retourne un CategoryInfo ou None si vide."""
    mp3_files = sorted(
        [f for f in directory.iterdir() if f.is_file() and f.suffix.lower() == ".mp3"],
        key=lambda f: f.name,
    )

    # Vérifier les fichiers MP3 vides
    for mp3 in mp3_files:
        if mp3.stat().st_size == 0:
            report.valid = False
            report.errors.append(f"Le fichier MP3 est vide (0 octets) : {mp3}")

    # Descendre dans les sous-dossiers
    subdirs = sorted(
        [d for d in directory.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )

    subcategories: list[CategoryInfo] = []
    for subdir in subdirs:
        sub = _validate_directory(subdir, report)
        if sub is not None:
            subcategories.append(sub)

    # Si ni MP3 ni sous-catégories valides → ignorer avec warning
    if not mp3_files and not subcategories:
        report.warnings.append(
            f"Le dossier '{directory.name}' ne contient aucun fichier .mp3 ni sous-dossier utile — ignoré."
        )
        return None

    return CategoryInfo(
        name=directory.name,
        path=directory,
        mp3_files=mp3_files,
        subcategories=subcategories,
    )
