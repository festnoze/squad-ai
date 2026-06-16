"""L2g-1: per-language toolchain command building + output parsing."""

from autospec.orchestrator import toolchain


def test_normalize_unknown_falls_back_to_python():
    assert toolchain.normalize("cobol") == "python"
    assert toolchain.normalize(None) == "python"
    assert toolchain.normalize("GO") == "go"
    assert toolchain.normalize("rust") == "rust"


def test_test_command_per_language():
    assert toolchain.test_command("go", "/tmp/r.json")[:3] == ["go", "test", "./..."]
    assert toolchain.test_command("rust", "/tmp/r.json")[:2] == ["cargo", "test"]
    py = toolchain.test_command("python", "/tmp/r.json")
    assert "pytest" in py and "--json-report-file=/tmp/r.json" in py


def test_run_command_per_language():
    assert toolchain.run_command("go") == ["go", "run", "."]
    assert toolchain.run_command("rust") == ["cargo", "run", "-q"]
    assert toolchain.run_command("python")[:3] == ["uv", "run", "python"]


def test_needs_report_file_only_python():
    assert toolchain.needs_report_file("python")
    assert not toolchain.needs_report_file("go")
    assert not toolchain.needs_report_file("rust")


def test_parse_go_json_events():
    stdout = "\n".join(
        [
            '{"Action":"run","Package":"app","Test":"TestAdd"}',
            '{"Action":"pass","Package":"app","Test":"TestAdd"}',
            '{"Action":"run","Package":"app","Test":"TestSub"}',
            '{"Action":"fail","Package":"app","Test":"TestSub"}',
            '{"Action":"skip","Package":"app","Test":"TestSkip"}',
            "ok  \tapp\t0.2s",  # non-JSON line ignored
        ]
    )
    res = toolchain.parse_results("go", stdout, "")
    assert res == {
        "app::TestAdd": "passed",
        "app::TestSub": "failed",
        "app::TestSkip": "skipped",
    }


def test_parse_go_ignores_build_errors():
    # A compile failure prints non-JSON to stdout — parser must not choke.
    res = toolchain.parse_results("go", "app/main.go:3:1: syntax error", "")
    assert res == {}


def test_parse_rust_text_output():
    stdout = "\n".join(
        [
            "running 3 tests",
            "test tests::adds_two ... ok",
            "test tests::subtracts ... FAILED",
            "test tests::pending ... ignored",
            "test result: FAILED. 1 passed; 1 failed; 1 ignored",
        ]
    )
    res = toolchain.parse_results("rust", stdout, "")
    assert res == {
        "tests::adds_two": "passed",
        "tests::subtracts": "failed",
        "tests::pending": "skipped",
    }
