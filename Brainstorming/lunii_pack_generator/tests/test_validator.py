"""Tests pour le module validator."""

from pathlib import Path

from lunii_pack_generator.validator import validate_source


def _create_tree(tmp_path: Path, structure: dict) -> Path:
    """Crée une arborescence depuis un dict imbriqué.

    Clés = noms de dossiers, valeurs = dict (sous-dossiers) ou list[str] (fichiers).
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
                (path / fname).write_bytes(b"\xff" * 100)


class TestValidateSourceNominal:
    """Cas nominaux."""

    def test_valid_flat_tree(self, tmp_path):
        source = _create_tree(tmp_path, {
            "01 - Aventures": ["01.mp3", "02.mp3", "03.mp3"],
            "02 - Contes": ["01.mp3", "02.mp3"],
        })
        report = validate_source(source)

        assert report.valid is True
        assert len(report.categories) == 2
        assert report.total_stories == 5
        assert report.errors == []

    def test_single_category(self, tmp_path):
        source = _create_tree(tmp_path, {
            "01 - Seule": ["01.mp3"],
        })
        report = validate_source(source)

        assert report.valid is True
        assert len(report.categories) == 1
        assert report.total_stories == 1

    def test_nested_structure(self, tmp_path):
        source = _create_tree(tmp_path, {
            "01 - Tome 1": {
                "01 - Chapitre 1": ["01.mp3", "02.mp3"],
                "02 - Chapitre 2": ["01.mp3"],
            },
            "02 - Tome 2": ["01.mp3", "02.mp3"],
        })
        report = validate_source(source)

        assert report.valid is True
        assert len(report.categories) == 2
        assert report.total_stories == 5

        tome1 = report.categories[0]
        assert len(tome1.subcategories) == 2
        assert tome1.total_stories == 3
        assert len(tome1.mp3_files) == 0

        tome2 = report.categories[1]
        assert len(tome2.subcategories) == 0
        assert tome2.total_stories == 2
        assert len(tome2.mp3_files) == 2

    def test_deep_nesting(self, tmp_path):
        source = _create_tree(tmp_path, {
            "01 - Niveau 1": {
                "01 - Niveau 2": {
                    "01 - Niveau 3": ["01.mp3"],
                },
            },
        })
        report = validate_source(source)

        assert report.valid is True
        assert report.total_stories == 1

        lvl1 = report.categories[0]
        assert len(lvl1.subcategories) == 1
        lvl2 = lvl1.subcategories[0]
        assert len(lvl2.subcategories) == 1
        lvl3 = lvl2.subcategories[0]
        assert len(lvl3.mp3_files) == 1


class TestValidateSourceErrors:
    """Cas d'erreur."""

    def test_source_does_not_exist(self, tmp_path):
        report = validate_source(tmp_path / "inexistant")

        assert report.valid is False
        assert len(report.errors) == 1
        assert "n'existe pas" in report.errors[0]

    def test_source_is_a_file(self, tmp_path):
        f = tmp_path / "not_a_dir.txt"
        f.write_text("hello")
        report = validate_source(f)

        assert report.valid is False
        assert "pas un dossier" in report.errors[0]

    def test_empty_source_no_categories(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        report = validate_source(source)

        assert report.valid is False
        assert "Aucune catégorie" in report.errors[0]

    def test_category_without_mp3_is_skipped(self, tmp_path):
        source = _create_tree(tmp_path, {
            "01 - Vide": {},
            "02 - Valide": ["01.mp3"],
        })
        (source / "01 - Vide" / "readme.txt").write_text("pas un mp3")
        report = validate_source(source)

        assert report.valid is True
        assert len(report.categories) == 1
        assert report.categories[0].name == "02 - Valide"
        assert any("ignoré" in w for w in report.warnings)

    def test_all_categories_empty(self, tmp_path):
        source = _create_tree(tmp_path, {
            "01 - Vide": {},
        })
        report = validate_source(source)

        assert report.total_stories == 0
        assert len(report.categories) == 0

    def test_empty_mp3_file(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        cat = source / "01 - Cat"
        cat.mkdir()
        (cat / "01.mp3").write_bytes(b"")  # 0 octets
        report = validate_source(source)

        assert report.valid is False
        assert "vide" in report.errors[0].lower()


class TestValidateSourceNested:
    """Structure imbriquée."""

    def test_nested_empty_subdir_skipped(self, tmp_path):
        source = _create_tree(tmp_path, {
            "01 - Tome": {
                "01 - OK": ["01.mp3"],
                "02 - Vide": {},
            },
        })
        report = validate_source(source)

        assert report.valid is True
        assert report.total_stories == 1
        tome = report.categories[0]
        assert len(tome.subcategories) == 1  # "02 - Vide" ignoré
        assert any("ignoré" in w for w in report.warnings)

    def test_mixed_mp3_and_subdirs(self, tmp_path):
        """Un dossier peut contenir à la fois des MP3 et des sous-dossiers."""
        source = _create_tree(tmp_path, {
            "01 - Mix": {
                "01 - Sub": ["01.mp3"],
            },
        })
        # Ajouter un MP3 au niveau du dossier Mix lui-même
        (source / "01 - Mix" / "bonus.mp3").write_bytes(b"\xff" * 100)
        report = validate_source(source)

        assert report.valid is True
        mix = report.categories[0]
        assert len(mix.mp3_files) == 1  # bonus.mp3
        assert len(mix.subcategories) == 1
        assert mix.total_stories == 2  # bonus.mp3 + 01 - Sub/01.mp3
