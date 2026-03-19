"""Appel subprocess à studio-pack-generator via Deno et gestion du .zip généré."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from rich.console import Console

from lunii_pack_generator.utils import detect_deno, detect_spg_source, format_size

console = Console()


class GeneratorError(Exception):
    """Erreur lors de la génération du pack."""


def build_command(
    deno_path: Path,
    spg_entry: Path,
    source_dir: Path,
    *,
    lang: str = "fr",
    delay: bool = True,
    auto_next: bool = True,
) -> list[str]:
    """Construit la commande deno run pour studio-pack-generator."""
    cmd = [str(deno_path), "run", "-A", str(spg_entry.resolve())]

    if lang:
        cmd.extend(["--lang", lang])

    if delay:
        cmd.append("--add-delay")

    if auto_next:
        cmd.append("--auto-next-story-transition")

    cmd.append(str(source_dir))

    return cmd


def find_generated_zip(source_dir: Path) -> Path | None:
    """Cherche le .zip généré par studio-pack-generator.

    Le zip est typiquement créé à côté du dossier source ou dans un sous-dossier.
    """
    parent = source_dir.parent

    # Chercher dans le dossier parent du source
    for candidate in parent.glob("*.zip"):
        if source_dir.name.lower() in candidate.name.lower() or "pack" in candidate.name.lower():
            return candidate

    # Chercher plus largement : tout .zip récent dans le parent
    zips = sorted(parent.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    if zips:
        return zips[0]

    # Chercher dans le dossier source lui-même
    zips = sorted(source_dir.rglob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    if zips:
        return zips[0]

    return None


def run_generation(
    source_dir: Path,
    output_dir: Path,
    bin_dir: Path | None = None,
    *,
    lang: str = "fr",
    delay: bool = True,
    auto_next: bool = True,
) -> Path:
    """Lance la génération du pack via deno run et retourne le chemin du .zip final.

    Raises:
        GeneratorError: Si deno ou les sources sont absents, ou si la génération échoue.
    """
    # Résoudre deno
    deno_path = detect_deno()
    if deno_path is None:
        raise GeneratorError(
            "Deno introuvable dans le PATH.\n"
            "Installez-le : https://docs.deno.com/runtime/getting_started/installation/"
        )

    # Résoudre les sources studio-pack-generator
    spg_entry = detect_spg_source(bin_dir)
    if spg_entry is None:
        raise GeneratorError(
            "Sources studio-pack-generator introuvables.\n"
            "Placez les sources dans ./bin/ (avec studio_pack_generator.ts).\n"
            "Voir : https://github.com/jersou/studio-pack-generator"
        )

    console.print(f"[dim]Deno : {deno_path}[/dim]")
    console.print(f"[dim]SPG  : {spg_entry}[/dim]")

    # Construire la commande
    cmd = build_command(
        deno_path,
        spg_entry,
        source_dir,
        lang=lang,
        delay=delay,
        auto_next=auto_next,
    )
    console.print(f"[dim]Commande : {' '.join(cmd)}[/dim]\n")

    # Exécuter
    console.rule("[bold blue]studio-pack-generator")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(source_dir.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise GeneratorError(f"Impossible de lancer le binaire : {exc}") from exc

    # Afficher la sortie
    if result.stdout:
        console.print(result.stdout)

    if result.returncode != 0:
        raise GeneratorError(
            f"studio-pack-generator a échoué (code retour : {result.returncode})"
        )

    console.rule("[bold green]Génération terminée")

    # Trouver et déplacer le .zip
    zip_path = find_generated_zip(source_dir)
    if zip_path is None:
        raise GeneratorError(
            "La génération semble avoir réussi mais aucun fichier .zip n'a été trouvé."
        )

    # Déplacer dans output/
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / zip_path.name
    shutil.move(str(zip_path), str(dest))

    size = format_size(dest.stat().st_size)
    console.print(f"\n[bold green]Pack généré :[/bold green] {dest}")
    console.print(f"[bold green]Taille :[/bold green] {size}")

    return dest
