"""Normalisation de l'arborescence source : ajout des préfixes numériques."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_NUMERIC_PREFIX_RE = re.compile(r"^\d+\s*-\s*")


@dataclass
class RenameAction:
    """Un renommage effectué."""

    old_path: Path
    new_path: Path
    old_name: str
    new_name: str


def normalize_source(source_dir: Path) -> list[RenameAction]:
    """Renomme récursivement les dossiers sans préfixe numérique.

    À chaque niveau, les dossiers sont triés par nom. Ceux qui n'ont
    pas de préfixe numérique reçoivent un préfixe basé sur leur position
    dans l'ordre trié (01 - , 02 - , etc.).

    Retourne la liste des renommages effectués.
    """
    renames: list[RenameAction] = []
    _normalize_level(source_dir, renames)
    return renames


def _normalize_level(directory: Path, renames: list[RenameAction]) -> None:
    """Normalise un niveau de l'arborescence, puis descend récursivement."""
    subdirs = sorted(
        [d for d in directory.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )

    if not subdirs:
        return

    # Renommer les dossiers sans préfixe à ce niveau
    renamed_dirs = _rename_dirs_at_level(subdirs, renames)

    # Descendre récursivement dans chaque sous-dossier (après renommage)
    for subdir in renamed_dirs:
        _normalize_level(subdir, renames)


def _rename_dirs_at_level(
    subdirs: list[Path], renames: list[RenameAction]
) -> list[Path]:
    """Renomme les dossiers sans préfixe numérique à un niveau donné.

    Retourne la liste mise à jour des chemins (après renommage éventuel).
    """
    result: list[Path] = []
    width = len(str(len(subdirs)))  # ex: 2 chiffres si ≤99 dossiers

    for idx, subdir in enumerate(subdirs, start=1):
        if _NUMERIC_PREFIX_RE.match(subdir.name):
            # Déjà préfixé, on garde tel quel
            result.append(subdir)
            continue

        prefix = str(idx).zfill(max(width, 2))
        new_name = f"{prefix} - {subdir.name}"
        new_path = subdir.parent / new_name

        # Éviter les collisions
        if new_path.exists() and new_path != subdir:
            new_name = f"{prefix} - {subdir.name} (renommé)"
            new_path = subdir.parent / new_name

        subdir.rename(new_path)
        renames.append(RenameAction(
            old_path=subdir,
            new_path=new_path,
            old_name=subdir.name,
            new_name=new_name,
        ))
        result.append(new_path)

    return result
