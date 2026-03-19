"""Helpers : détection Deno, source studio-pack-generator, formatage."""

from __future__ import annotations

import shutil
from pathlib import Path

# Point d'entrée TypeScript de studio-pack-generator
SPG_ENTRY_POINT = "studio_pack_generator.ts"


def detect_deno() -> Path | None:
    """Cherche le binaire deno dans le PATH."""
    found = shutil.which("deno")
    if found:
        return Path(found)
    return None


def detect_spg_source(bin_dir: Path | None = None) -> Path | None:
    """Cherche studio_pack_generator.ts dans bin/.

    Ordre de recherche :
    1. Dossier personnalisé fourni
    2. ./bin/studio_pack_generator.ts
    """
    candidates: list[Path] = []
    if bin_dir:
        candidates.append(bin_dir / SPG_ENTRY_POINT)
    candidates.append(Path("bin") / SPG_ENTRY_POINT)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def format_size(size_bytes: int) -> str:
    """Formate une taille en octets en une chaîne lisible (Ko, Mo, Go)."""
    if size_bytes < 1024:
        return f"{size_bytes} o"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} Ko"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} Mo"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} Go"
