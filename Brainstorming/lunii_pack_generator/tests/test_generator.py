"""Tests pour le module generator."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lunii_pack_generator.generator import (
    GeneratorError,
    build_command,
    find_generated_zip,
    run_generation,
)


class TestBuildCommand:
    """Tests de construction de la commande deno run."""

    def test_default_options(self, tmp_path):
        deno = tmp_path / "deno"
        spg = tmp_path / "studio_pack_generator.ts"
        source = tmp_path / "source"
        cmd = build_command(deno, spg, source)

        assert cmd[0] == str(deno)
        assert cmd[1] == "run"
        assert cmd[2] == "-A"
        assert str(spg.resolve()) in cmd[3]
        assert "--lang" in cmd
        assert "fr" in cmd
        assert "--add-delay" in cmd
        assert "--auto-next-story-transition" in cmd
        assert cmd[-1] == str(source)

    def test_no_delay(self, tmp_path):
        deno = tmp_path / "deno"
        spg = tmp_path / "spg.ts"
        source = tmp_path / "source"
        cmd = build_command(deno, spg, source, delay=False)

        assert "--add-delay" not in cmd

    def test_no_auto_next(self, tmp_path):
        deno = tmp_path / "deno"
        spg = tmp_path / "spg.ts"
        source = tmp_path / "source"
        cmd = build_command(deno, spg, source, auto_next=False)

        assert "--auto-next-story-transition" not in cmd

    def test_custom_lang(self, tmp_path):
        deno = tmp_path / "deno"
        spg = tmp_path / "spg.ts"
        source = tmp_path / "source"
        cmd = build_command(deno, spg, source, lang="en")

        idx = cmd.index("--lang")
        assert cmd[idx + 1] == "en"


class TestFindGeneratedZip:
    """Tests de recherche du .zip généré."""

    def test_zip_in_parent(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        zip_file = tmp_path / "source.zip"
        zip_file.write_bytes(b"PK\x03\x04")

        result = find_generated_zip(source)
        assert result == zip_file

    def test_zip_in_source(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        zip_file = source / "pack.zip"
        zip_file.write_bytes(b"PK\x03\x04")

        result = find_generated_zip(source)
        assert result is not None

    def test_no_zip_found(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()

        result = find_generated_zip(source)
        assert result is None


class TestRunGeneration:
    """Tests de la génération avec mock subprocess."""

    def test_deno_not_found_raises(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        output = tmp_path / "output"

        with patch("lunii_pack_generator.generator.detect_deno", return_value=None):
            with pytest.raises(GeneratorError, match="Deno introuvable"):
                run_generation(source, output)

    def test_spg_source_not_found_raises(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        output = tmp_path / "output"
        deno = tmp_path / "deno"

        with (
            patch("lunii_pack_generator.generator.detect_deno", return_value=deno),
            patch("lunii_pack_generator.generator.detect_spg_source", return_value=None),
        ):
            with pytest.raises(GeneratorError, match="introuvables"):
                run_generation(source, output)

    def test_subprocess_failure_raises(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        output = tmp_path / "output"
        deno = tmp_path / "deno"
        spg = tmp_path / "studio_pack_generator.ts"
        spg.write_text("// entry")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "Error output"

        with (
            patch("lunii_pack_generator.generator.detect_deno", return_value=deno),
            patch("lunii_pack_generator.generator.detect_spg_source", return_value=spg),
            patch("subprocess.run", return_value=mock_result),
        ):
            with pytest.raises(GeneratorError, match="échoué"):
                run_generation(source, output)

    def test_successful_generation(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        output = tmp_path / "output"
        deno = tmp_path / "deno"
        spg = tmp_path / "studio_pack_generator.ts"
        spg.write_text("// entry")

        # Créer un faux .zip que la génération "produirait"
        fake_zip = tmp_path / "source.zip"
        fake_zip.write_bytes(b"PK\x03\x04" + b"\x00" * 100)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Pack generated!"

        with (
            patch("lunii_pack_generator.generator.detect_deno", return_value=deno),
            patch("lunii_pack_generator.generator.detect_spg_source", return_value=spg),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = run_generation(source, output)

        assert result.exists()
        assert result.suffix == ".zip"
        assert result.parent == output
