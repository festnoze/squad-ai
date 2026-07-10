"""Unit tests for the failure-signature normalizer (W0.5-SIG).

Pure module — no fixtures beyond plain dicts/strings.
"""

from autospec.orchestrator.signatures import (
    FLAKE,
    OUT_OF_SCOPE,
    SKELETON,
    TAMPERED,
    guard_signature,
    normalize_signature,
    same_failure,
    signatures_from_report,
)


# --------------------------------------------------------------- normalize

def test_normalize_stable_across_line_numbers():
    """Same logical failure, different traceback line numbers → same key."""
    a = normalize_signature("tests/test_x.py::test_a:42", "AssertionError")
    b = normalize_signature("tests/test_x.py::test_a:57", "AssertionError")
    assert a == b


def test_normalize_stable_across_tmp_paths():
    """Different tmp_path in a parametrized id → same key."""
    a = normalize_signature("tests/test_x.py::test_a[/tmp/pytest-of-u/abc/f]")
    b = normalize_signature("tests/test_x.py::test_a[/tmp/pytest-of-u/xyz/f]")
    assert a == b
    assert a != ""


def test_normalize_stable_across_windows_tmp_and_addr():
    """Windows temp paths and memory addresses are both scrubbed."""
    a = normalize_signature(
        r"tests/test_x.py::test_a", r"ValueError at 0x7fa3b21c C:\Users\e\Temp\pytest-of-e\1\x"
    )
    b = normalize_signature(
        r"tests/test_x.py::test_a", r"ValueError at 0x00 deadbeef99 C:\Users\e\Temp\pytest-of-e\9\y"
    )
    assert a == b


def test_normalize_case_insensitive():
    assert normalize_signature("tests/test_x.py::test_a", "AssertionError") == \
        normalize_signature("tests/test_x.py::test_a", "assertionerror")


def test_normalize_different_tests_differ():
    a = normalize_signature("tests/test_x.py::test_a", "AssertionError")
    b = normalize_signature("tests/test_x.py::test_b", "AssertionError")
    assert a != b


def test_normalize_empty_inputs():
    assert normalize_signature("", "") == ""
    assert normalize_signature("   ", "") == ""


def test_normalize_node_only():
    assert normalize_signature("tests/test_x.py::test_a") != ""


# ----------------------------------------------------- signatures_from_report

def _report():
    """Realistic pytest-json-report-style dict: 2 failed + 1 passed."""
    return {
        "created": 1_700_000_000.0,
        "exitcode": 1,
        "tests": [
            {
                "nodeid": "tests/test_math.py::test_add",
                "outcome": "passed",
                "call": {"outcome": "passed"},
            },
            {
                "nodeid": "tests/test_math.py::test_sub",
                "outcome": "failed",
                "call": {
                    "outcome": "failed",
                    "longrepr": (
                        "tests/test_math.py:31: in test_sub\n"
                        "    assert sub(2, 1) == 0\n"
                        "AssertionError: assert 1 == 0"
                    ),
                },
            },
            {
                "nodeid": "tests/test_io.py::test_read",
                "outcome": "error",
                "call": {
                    "outcome": "error",
                    "longrepr": {
                        "reprcrash": {
                            "path": "/tmp/pytest-of-x/1/test_read.py",
                            "lineno": 12,
                            "message": "FileNotFoundError: [Errno 2] No such file",
                        }
                    },
                },
            },
        ],
    }


def test_signatures_from_report_two_failures():
    sigs = signatures_from_report(_report())
    assert len(sigs) == 2  # passed test excluded, failed + error included


def test_signatures_from_report_carry_exc_type():
    sigs = signatures_from_report(_report())
    joined = " ".join(sigs)
    assert "assertionerror" in joined
    assert "filenotfounderror" in joined


def test_signatures_from_report_dedup():
    """A repeated logical failure yields one signature; order preserved."""
    rep = {
        "tests": [
            {"nodeid": "tests/t.py::test_a:10", "outcome": "failed",
             "call": {"longrepr": "AssertionError: x"}},
            {"nodeid": "tests/t.py::test_a:99", "outcome": "failed",
             "call": {"longrepr": "AssertionError: y"}},
            {"nodeid": "tests/t.py::test_b", "outcome": "failed",
             "call": {"longrepr": "ValueError: z"}},
        ]
    }
    sigs = signatures_from_report(rep)
    assert len(sigs) == 2
    # order-preserving: test_a's signature comes first.
    assert sigs[0] != sigs[1]


def test_signatures_from_report_tolerates_garbage():
    assert signatures_from_report({}) == []
    assert signatures_from_report({"tests": "not a list"}) == []
    assert signatures_from_report({"tests": [None, 42, {}]}) == []
    assert signatures_from_report("nope") == []  # type: ignore[arg-type]
    # entry missing nodeid is skipped
    assert signatures_from_report({"tests": [{"outcome": "failed"}]}) == []


# --------------------------------------------------------------- same_failure

def test_same_failure_overlap_true():
    a = ["sigA", "sigB"]
    b = ["sigB", "sigC"]
    assert same_failure(a, b) is True


def test_same_failure_no_overlap_false():
    assert same_failure(["sigA"], ["sigZ"]) is False


def test_same_failure_empty_false():
    assert same_failure([], ["sigA"]) is False
    assert same_failure(["sigA"], []) is False
    assert same_failure([], []) is False


def test_same_failure_recurring_across_attempts():
    """Two attempts that fail the same logical test → recurrence detected even
    though line numbers differ between runs."""
    attempt1 = signatures_from_report({
        "tests": [{"nodeid": "tests/t.py::test_a:10", "outcome": "failed",
                   "call": {"longrepr": "AssertionError: boom"}}]
    })
    attempt2 = signatures_from_report({
        "tests": [{"nodeid": "tests/t.py::test_a:88", "outcome": "failed",
                   "call": {"longrepr": "AssertionError: boom later"}}]
    })
    assert same_failure(attempt1, attempt2) is True


# --------------------------------------------------------------- guard_signature

def test_guard_signature_format():
    assert guard_signature(TAMPERED) == "guard:tampered:"
    assert guard_signature(OUT_OF_SCOPE, "src/other.py") == "guard:out_of_scope:src/other.py"
    assert guard_signature(SKELETON, "impl.py") == "guard:skeleton:impl.py"
    assert guard_signature(FLAKE) == "guard:flake:"


def test_guard_signature_detail_scrubbed_stable():
    """Volatile bits in the detail are stripped so the guard key is stable."""
    a = guard_signature(TAMPERED, "tests/test_x.py:42")
    b = guard_signature(TAMPERED, "tests/test_x.py:99")
    assert a == b


def test_guard_verdict_constants():
    assert TAMPERED == "tampered"
    assert OUT_OF_SCOPE == "out_of_scope"
    assert SKELETON == "skeleton"
    assert FLAKE == "flake"
