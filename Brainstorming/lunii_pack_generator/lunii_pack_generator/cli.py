"""Point d'entrée CLI — interface Click avec affichage Rich."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree

from lunii_pack_generator.generator import GeneratorError, run_generation
from lunii_pack_generator.normalizer import normalize_source
from lunii_pack_generator.utils import detect_deno, detect_spg_source, format_size
from lunii_pack_generator.validator import CategoryInfo, validate_source

console = Console()


def _add_category_to_tree(branch: Tree, category: CategoryInfo) -> None:
    """Ajoute récursivement une catégorie et ses enfants à l'arbre Rich."""
    for mp3 in category.mp3_files:
        size = format_size(mp3.stat().st_size)
        branch.add(f"[dim]{mp3.name}[/dim]  [green]{size}[/green]")
    for sub in category.subcategories:
        sub_branch = branch.add(
            f"[bold yellow]{sub.name}[/bold yellow] ({sub.total_stories} MP3)"
        )
        _add_category_to_tree(sub_branch, sub)


def _display_tree(report) -> None:
    """Affiche l'arborescence des catégories et histoires détectées."""
    tree = Tree(
        f"[bold cyan]Source[/bold cyan] — "
        f"{len(report.categories)} catégorie(s), {report.total_stories} histoire(s)"
    )
    for cat in report.categories:
        branch = tree.add(
            f"[bold yellow]{cat.name}[/bold yellow] ({cat.total_stories} MP3)"
        )
        _add_category_to_tree(branch, cat)

    console.print(Panel(tree, title="Arborescence détectée", border_style="blue"))


def _display_warnings(report) -> None:
    """Affiche les warnings de validation."""
    for warning in report.warnings:
        console.print(f"  [yellow]⚠ {warning}[/yellow]")


def _display_errors(report) -> None:
    """Affiche les erreurs de validation."""
    for error in report.errors:
        console.print(f"  [red]✗ {error}[/red]")


def _display_renames(renames) -> None:
    """Affiche les renommages effectués par le normalizer."""
    if not renames:
        return
    console.print(
        Panel(
            f"[bold]{len(renames)} dossier(s) renommé(s)[/bold]",
            border_style="yellow",
        )
    )
    for r in renames:
        console.print(f"  [yellow]→[/yellow] {r.old_name}  [dim]→[/dim]  [bold]{r.new_name}[/bold]")
    console.print()


def _check_system_deps() -> None:
    """Vérifie la disponibilité des dépendances système."""
    import shutil

    deps = {
        "deno": detect_deno(),
        "studio-pack-generator (sources)": detect_spg_source(),
        "ffmpeg": shutil.which("ffmpeg"),
        "convert (ImageMagick)": shutil.which("convert") or shutil.which("magick"),
    }

    console.print(Panel("[bold]Vérification des dépendances système[/bold]", border_style="blue"))
    all_ok = True
    for name, path in deps.items():
        if path:
            console.print(f"  [green]✓[/green] {name} → {path}")
        else:
            console.print(f"  [red]✗[/red] {name} — introuvable")
            all_ok = False

    if all_ok:
        console.print("\n[bold green]Toutes les dépendances sont disponibles.[/bold green]")
    else:
        console.print(
            "\n[bold yellow]Certaines dépendances sont manquantes. "
            "La génération pourrait échouer.[/bold yellow]"
        )


@click.command()
@click.option(
    "--source",
    type=click.Path(exists=False, path_type=Path),
    default=Path("./source"),
    show_default=True,
    help="Chemin vers le dossier source contenant les MP3.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=Path("./output"),
    show_default=True,
    help="Dossier de sortie pour le .zip généré.",
)
@click.option(
    "--bin",
    "bin_dir",
    type=click.Path(exists=False, path_type=Path),
    default=None,
    help="Chemin vers le dossier contenant les sources studio-pack-generator.",
)
@click.option(
    "--lang",
    default="fr",
    show_default=True,
    help="Langue TTS pour les titres de menus.",
)
@click.option(
    "--delay/--no-delay",
    default=True,
    show_default=True,
    help="Ajouter 1 seconde de silence en début/fin.",
)
@click.option(
    "--auto-next/--no-auto-next",
    default=True,
    show_default=True,
    help="Enchaînement automatique à la fin d'une histoire.",
)
@click.option(
    "--check-deps",
    is_flag=True,
    default=False,
    help="Vérifier les dépendances système et quitter.",
)
def main(
    source: Path,
    output: Path,
    bin_dir: Path | None,
    lang: str,
    delay: bool,
    auto_next: bool,
    check_deps: bool,
) -> None:
    """Génère un pack Lunii (.zip STUdio) depuis une arborescence de fichiers MP3."""
    console.print(
        Panel(
            "[bold]Lunii Pack Generator[/bold]\n"
            "Génère un pack STUdio depuis vos fichiers MP3",
            border_style="bright_blue",
        )
    )

    if check_deps:
        _check_system_deps()
        return

    console.print(f"\n[dim]Source : {source.resolve()}[/dim]")

    # Vérifier que le dossier source existe avant de normaliser
    if not source.exists() or not source.is_dir():
        console.print(f"  [red]✗ Le dossier source n'existe pas : {source}[/red]")
        sys.exit(1)

    # Normalisation — ajout des préfixes numériques manquants
    renames = normalize_source(source)
    _display_renames(renames)

    # Validation
    report = validate_source(source)

    if report.errors:
        _display_errors(report)
        console.print("\n[bold red]Validation échouée. Corrigez les erreurs ci-dessus.[/bold red]")
        sys.exit(1)

    _display_tree(report)

    if report.warnings:
        _display_warnings(report)
        console.print()

    # Confirmation
    if not click.confirm("Lancer la génération ?", default=True):
        console.print("[dim]Annulé.[/dim]")
        return

    # Génération
    console.print()
    try:
        zip_path = run_generation(
            source_dir=source,
            output_dir=output,
            bin_dir=bin_dir,
            lang=lang,
            delay=delay,
            auto_next=auto_next,
        )
    except GeneratorError as exc:
        console.print(f"\n[bold red]Erreur : {exc}[/bold red]")
        sys.exit(1)

    console.print(
        f"\n[bold green]Importez {zip_path.name} dans STUdio via 'Open from file'.[/bold green]"
    )


if __name__ == "__main__":
    main()
