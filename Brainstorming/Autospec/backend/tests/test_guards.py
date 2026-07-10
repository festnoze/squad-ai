"""Wave 0.5 anti-cheating detectors (orchestrator/guards.py).

Pure detection functions — no git, no filesystem, no pipeline. Each block
covers one detector: T05 test-tamper, T06 scope, T07 skeleton, T10 imports.
"""

from autospec.orchestrator import guards


# ------------------------------------------------------------- T05 test-tamper

def test_modified_test_files_flags_tests_default_heuristic():
    changed = ["tests/test_x.py", "src/app.py", "pkg/foo_test.py"]
    flagged = guards.modified_test_files(changed, test_globs=[])
    assert "tests/test_x.py" in flagged
    assert "pkg/foo_test.py" in flagged
    assert "src/app.py" not in flagged


def test_modified_test_files_respects_explicit_globs():
    changed = ["tests/test_x.py", "spec/thing.spec.py", "src/app.py"]
    flagged = guards.modified_test_files(changed, test_globs=["spec/*.spec.py"])
    assert flagged == ["spec/thing.spec.py"]


def test_modified_test_files_windows_paths_and_dedup():
    changed = ["tests\\test_x.py", "tests\\test_x.py", "src\\app.py"]
    flagged = guards.modified_test_files(changed, test_globs=[])
    assert flagged == ["tests\\test_x.py"]


# -------------------------------------------------------------------- T06 scope

def test_out_of_scope_dir_prefix_covers_child_flags_sibling():
    changed = ["src/app.py", "other/thing.py"]
    claims = ["src/"]
    out = guards.out_of_scope_paths(changed, claims)
    assert out == ["other/thing.py"]


def test_out_of_scope_bare_dir_is_segment_wise():
    # "src" must NOT cover "srcutil.py".
    out = guards.out_of_scope_paths(["srcutil.py", "src/a.py"], ["src"])
    assert out == ["srcutil.py"]


def test_out_of_scope_exact_and_glob_claims():
    changed = ["a/b.py", "a/c.py", "d/e.py"]
    claims = ["a/b.py", "a/*.py"]
    assert guards.out_of_scope_paths(changed, claims) == ["d/e.py"]


def test_out_of_scope_empty_claims_enforces_nothing():
    assert guards.out_of_scope_paths(["anything/at/all.py"], []) == []


# ----------------------------------------------------------------- T07 skeleton

def test_skeleton_pass_only_body_flagged():
    src = "def foo():\n    pass\n"
    findings = guards.detect_skeleton(src, "m.py")
    assert any("skeleton body" in f and "foo" in f for f in findings)


def test_skeleton_ellipsis_and_notimplemented_and_docstring():
    src = (
        "def a():\n    ...\n"
        "def b():\n    raise NotImplementedError\n"
        "def c():\n    'just a docstring'\n"
    )
    findings = guards.detect_skeleton(src, "m.py")
    joined = "\n".join(findings)
    assert "a()" in joined and "b()" in joined and "c()" in joined
    assert findings and all("skeleton body" in f for f in findings)


def test_skeleton_real_body_not_flagged():
    src = "def foo(x):\n    y = x + 1\n    return y\n"
    assert guards.detect_skeleton(src, "m.py") == []


def test_skeleton_hardcoded_return_flagged():
    src = "def answer():\n    return 42\n"
    findings = guards.detect_skeleton(src, "m.py")
    assert any("hardcoded return" in f and "answer" in f for f in findings)


def test_skeleton_hardcoded_literal_container_flagged():
    src = "def rows():\n    return [1, 2, 3]\n"
    findings = guards.detect_skeleton(src, "m.py")
    assert any("hardcoded return" in f for f in findings)


def test_skeleton_dunder_return_literal_not_flagged():
    src = "class C:\n    def __len__(self):\n        return 0\n"
    assert guards.detect_skeleton(src, "m.py") == []


def test_skeleton_pytest_skip_call_flagged():
    src = "import pytest\ndef test_it():\n    pytest.skip('later')\n    assert True\n"
    findings = guards.detect_skeleton(src, "test_m.py")
    assert any("test skip" in f and "pytest.skip" in f for f in findings)


def test_skeleton_pytest_mark_skip_and_xfail_flagged():
    src = (
        "import pytest\n"
        "@pytest.mark.skip\n"
        "def test_a():\n    assert works()\n"
        "@pytest.mark.xfail(reason='x')\n"
        "def test_b():\n    assert works()\n"
    )
    findings = guards.detect_skeleton(src, "test_m.py")
    joined = "\n".join(findings)
    assert "@pytest.mark.skip" in joined
    assert "@pytest.mark.xfail" in joined


def test_skeleton_syntax_error_returns_empty():
    assert guards.detect_skeleton("def broken(:\n    pass\n", "m.py") == []


def test_skeleton_non_python_filename_returns_empty():
    assert guards.detect_skeleton("def foo():\n    pass\n", "notes.txt") == []


# ------------------------------------------------------------------ T10 imports

def test_imports_hallucinated_flagged():
    src = "import leftpadpkg\n"
    stdlib = guards.default_stdlib()
    out = guards.unresolved_imports(src, declared_deps=set(), stdlib_modules=stdlib)
    assert out == ["leftpadpkg"]


def test_imports_stdlib_not_flagged():
    src = "import os\nimport sys\nfrom pathlib import Path\n"
    stdlib = guards.default_stdlib()
    assert guards.unresolved_imports(src, set(), stdlib) == []


def test_imports_declared_dep_not_flagged():
    src = "import requests\nfrom requests.adapters import HTTPAdapter\n"
    stdlib = guards.default_stdlib()
    out = guards.unresolved_imports(src, declared_deps={"requests"}, stdlib_modules=stdlib)
    assert out == []


def test_imports_local_module_not_flagged():
    src = "from myapp.core import thing\nimport myapp\n"
    stdlib = guards.default_stdlib()
    out = guards.unresolved_imports(
        src, declared_deps=set(), stdlib_modules=stdlib, local_modules={"myapp"}
    )
    assert out == []


def test_imports_dotted_normalised_to_top_package():
    src = "import a.b.c\n"
    stdlib = guards.default_stdlib()
    assert guards.unresolved_imports(src, set(), stdlib) == ["a"]


def test_imports_relative_never_flagged():
    src = "from . import sibling\nfrom .util import helper\n"
    stdlib = guards.default_stdlib()
    assert guards.unresolved_imports(src, set(), stdlib) == []


def test_imports_syntax_error_returns_empty():
    stdlib = guards.default_stdlib()
    assert guards.unresolved_imports("import (", set(), stdlib) == []


def test_default_stdlib_has_common_modules():
    s = guards.default_stdlib()
    assert {"os", "sys", "json"} <= s
