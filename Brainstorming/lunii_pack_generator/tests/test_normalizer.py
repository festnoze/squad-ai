"""Tests pour le module normalizer."""

from pathlib import Path

from lunii_pack_generator.normalizer import normalize_source


def _create_tree(tmp_path: Path, structure: dict) -> Path:
    """Crée une arborescence depuis un dict imbriqué.

    Clés = noms de dossiers, valeurs = dict (sous-dossiers) ou list[str] (fichiers).
    Ex: {"Tome 1": {"Chap 1": ["01.mp3"]}, "Tome 2": ["01.mp3"]}
    """
    source = tmp_path / "source"
    source.mkdir()
    _build(source, structure)
    return source


def _build(parent: Path, structure: dict) -> None:
    for name, content in structure.items():
        path = parent / name
        path.mkdir(exist_ok=True)
        if isinstance(content, dict):
            _build(path, content)
        elif isinstance(content, list):
            for fname in content:
                (path / fname).write_bytes(b"\xff" * 50)


class TestNormalizeSimple:
    """Renommage au premier niveau."""

    def test_adds_prefix_to_all(self, tmp_path):
        source = _create_tree(tmp_path, {
            "Aventures": ["01.mp3"],
            "Contes": ["01.mp3"],
            "Fables": ["01.mp3"],
        })
        renames = normalize_source(source)

        assert len(renames) == 3
        dirs = sorted(d.name for d in source.iterdir() if d.is_dir())
        assert dirs == ["01 - Aventures", "02 - Contes", "03 - Fables"]

    def test_skips_already_prefixed(self, tmp_path):
        source = _create_tree(tmp_path, {
            "01 - Aventures": ["01.mp3"],
            "Contes": ["01.mp3"],
        })
        renames = normalize_source(source)

        assert len(renames) == 1
        assert renames[0].old_name == "Contes"
        assert "02" in renames[0].new_name

    def test_no_rename_needed(self, tmp_path):
        source = _create_tree(tmp_path, {
            "01 - A": ["01.mp3"],
            "02 - B": ["01.mp3"],
        })
        renames = normalize_source(source)
        assert renames == []


class TestNormalizeRecursive:
    """Renommage récursif dans les sous-dossiers."""

    def test_renames_nested_dirs(self, tmp_path):
        source = _create_tree(tmp_path, {
            "Tome 1": {
                "Chapitre A": ["01.mp3"],
                "Chapitre B": ["01.mp3"],
            },
            "Tome 2": {
                "Episode X": ["01.mp3"],
            },
        })
        renames = normalize_source(source)

        # 2 tomes + 2 chapitres + 1 épisode = 5 renommages
        assert len(renames) == 5

        # Vérifier la structure résultante
        top = sorted(d.name for d in source.iterdir() if d.is_dir())
        assert top == ["01 - Tome 1", "02 - Tome 2"]

        tome1 = source / "01 - Tome 1"
        subs = sorted(d.name for d in tome1.iterdir() if d.is_dir())
        assert subs == ["01 - Chapitre A", "02 - Chapitre B"]

    def test_mixed_nested_levels(self, tmp_path):
        source = _create_tree(tmp_path, {
            "01 - Déjà OK": {
                "Sans préfixe": ["01.mp3"],
            },
        })
        renames = normalize_source(source)

        # Seul "Sans préfixe" doit être renommé
        assert len(renames) == 1
        assert renames[0].old_name == "Sans préfixe"


class TestNormalizeEdgeCases:

    def test_empty_source(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        renames = normalize_source(source)
        assert renames == []

    def test_only_files_no_dirs(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "01.mp3").write_bytes(b"\xff")
        renames = normalize_source(source)
        assert renames == []
