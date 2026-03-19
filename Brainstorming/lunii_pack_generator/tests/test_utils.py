"""Tests pour le module utils."""

from pathlib import Path

from lunii_pack_generator.utils import (
    detect_deno,
    detect_spg_source,
    format_size,
)


class TestDetectDeno:
    """Tests de détection de deno."""

    def test_found_in_path(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/deno" if name == "deno" else None)
        result = detect_deno()
        assert result == Path("/usr/bin/deno")

    def test_not_found(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: None)
        result = detect_deno()
        assert result is None


class TestDetectSpgSource:
    """Tests de détection des sources studio-pack-generator."""

    def test_found_in_custom_dir(self, tmp_path):
        entry = tmp_path / "studio_pack_generator.ts"
        entry.write_text("// entry")
        result = detect_spg_source(tmp_path)
        assert result == entry

    def test_found_in_default_bin(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        entry = bin_dir / "studio_pack_generator.ts"
        entry.write_text("// entry")
        result = detect_spg_source()
        assert result is not None
        assert result.resolve() == entry.resolve()

    def test_not_found(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = detect_spg_source()
        assert result is None


class TestFormatSize:
    """Tests du formatage de taille."""

    def test_bytes(self):
        assert format_size(500) == "500 o"

    def test_kilobytes(self):
        assert format_size(1536) == "1.5 Ko"

    def test_megabytes(self):
        assert format_size(5 * 1024 * 1024) == "5.0 Mo"

    def test_gigabytes(self):
        assert format_size(2 * 1024 * 1024 * 1024) == "2.00 Go"

    def test_zero(self):
        assert format_size(0) == "0 o"

    def test_exact_1kb(self):
        assert format_size(1024) == "1.0 Ko"

    def test_exact_1mb(self):
        assert format_size(1024 * 1024) == "1.0 Mo"
