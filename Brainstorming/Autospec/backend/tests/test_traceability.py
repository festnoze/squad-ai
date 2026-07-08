"""Tests for the AC ↔ test traceability module (W2.0)."""

from __future__ import annotations

from autospec.orchestrator import traceability

ac_ids_in_source = traceability.ac_ids_in_source
coverage_report = traceability.coverage_report
map_acs_to_tests = traceability.map_acs_to_tests
# Bound to a non-``test_`` name so pytest does not collect the public API
# function itself as a test case.
functions_with_acs = traceability.test_functions_with_acs


# --------------------------------------------------------------- ac_ids_in_source

def test_ac_ids_from_docstring():
    source = '''
def test_login():
    """Verifies the login flow. AC: US-3.2"""
    assert True
'''
    assert ac_ids_in_source(source) == {"US-3.2"}


def test_ac_ids_from_comment():
    source = """
# AC: US-3.2
def test_login():
    assert True
"""
    assert ac_ids_in_source(source) == {"US-3.2"}


def test_ac_ids_comma_separated():
    source = """
# AC: US-3.2, US-3.3, AC1
def test_login():
    assert True
"""
    assert ac_ids_in_source(source) == {"US-3.2", "US-3.3", "AC1"}


def test_ac_ids_empty_and_garbage():
    assert ac_ids_in_source("") == set()
    assert ac_ids_in_source("this is just prose with no markers") == set()
    assert ac_ids_in_source("def (((broken python") == set()


# ------------------------------------------------------- test_functions_with_acs

def test_function_mapping_docstring():
    source = '''
def test_login():
    """AC: US-3.2"""
    assert True

def test_logout():
    """AC: US-3.4, US-3.5"""
    assert True
'''
    result = functions_with_acs(source)
    assert result == {
        "test_login": {"US-3.2"},
        "test_logout": {"US-3.4", "US-3.5"},
    }


def test_function_mapping_preceding_comment():
    source = """
# AC: US-3.2
def test_login():
    assert True
"""
    result = functions_with_acs(source)
    assert result == {"test_login": {"US-3.2"}}


def test_function_mapping_ignores_non_test_functions():
    source = '''
# AC: US-9.9
def helper():
    """AC: US-1.1"""
    return 1

def test_real():
    """AC: US-3.2"""
    assert True
'''
    result = functions_with_acs(source)
    assert "helper" not in result
    assert result["test_real"] == {"US-3.2"}


def test_function_mapping_no_markers_is_empty_set():
    source = """
def test_plain():
    assert True
"""
    # The test function is present, but declares no AC.
    assert functions_with_acs(source) == {"test_plain": set()}


def test_file_with_no_markers_yields_empty_ids():
    source = """
def test_a():
    assert 1 == 1

def test_b():
    assert 2 == 2
"""
    assert ac_ids_in_source(source) == set()
    result = functions_with_acs(source)
    assert all(ids == set() for ids in result.values())


def test_syntax_error_tolerance():
    broken = "def test_x(:\n    assert"
    assert functions_with_acs(broken) == {}
    assert functions_with_acs("") == {}


# ------------------------------------------------------------ map_acs_to_tests

def test_map_acs_across_two_files():
    sources = {
        "tests/test_login.py": '''
def test_login():
    """AC: US-3.2"""
    assert True
''',
        "tests/test_session.py": """
# AC: US-3.2, US-3.3
def test_session():
    assert True
""",
    }
    mapping = map_acs_to_tests(sources)
    assert mapping == {
        "US-3.2": ["tests/test_login.py", "tests/test_session.py"],
        "US-3.3": ["tests/test_session.py"],
    }


def test_map_acs_dedupes_and_sorts():
    sources = {
        "z_file.py": "# AC: AC1\ndef test_z(): pass\n",
        "a_file.py": '# AC: AC1\ndef test_a():\n    """AC: AC1"""\n    pass\n',
    }
    mapping = map_acs_to_tests(sources)
    assert mapping == {"AC1": ["a_file.py", "z_file.py"]}


# ------------------------------------------------------------- coverage_report

def test_coverage_report_covered_uncovered_orphan():
    all_ac_ids = {"US-3.2", "US-3.3", "US-3.4"}
    sources = {
        "tests/test_a.py": '''
def test_covered():
    """AC: US-3.2"""
    assert True
''',
        "tests/test_b.py": """
# AC: US-9.9
def test_orphan():
    assert True
""",
    }
    report = coverage_report(all_ac_ids, sources)
    assert report == {
        "covered": ["US-3.2"],
        "uncovered": ["US-3.3", "US-3.4"],
        "orphans": ["US-9.9"],
    }


def test_coverage_report_empty_inputs():
    assert coverage_report(set(), {}) == {
        "covered": [],
        "uncovered": [],
        "orphans": [],
    }


def test_coverage_report_all_referenced_are_orphans_when_none_declared():
    sources = {"tests/test_a.py": "# AC: US-1.1\ndef test_a(): pass\n"}
    report = coverage_report(set(), sources)
    assert report == {"covered": [], "uncovered": [], "orphans": ["US-1.1"]}
