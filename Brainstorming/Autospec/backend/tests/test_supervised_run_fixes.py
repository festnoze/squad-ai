"""Fixes issus du run supervisé « recettes » du 2026-07-20 (DEFECTS_RESOLUTION_PLAN.md).

Couvre les fixes déterministes hors gate : le .gitignore du scaffold ignore les
bases SQLite (D6), le marqueur d'infra « pipe refusé » du daemon Docker (PRE-1),
et le parseur des échecs de merge pré-conflit (D8).
"""

from __future__ import annotations

from autospec.orchestrator import docker_deploy, workspace
from autospec.orchestrator.pipeline import _parse_overwritten_files


# ------------------------------------------------------------------ D6 gitignore

def test_gitignore_template_ignores_sqlite_artifacts():
    """Un artefact SQLite créé par les tests (recipes.db) ne doit JAMAIS être
    commitable : traqué, il a cassé 3 merges du run supervisé (conflit binaire,
    modify/delete, « local changes would be overwritten »)."""
    for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
        assert pattern in workspace.GITIGNORE_TEMPLATE


# ------------------------------------------------- PRE-1 marqueur pipe refusé

def test_docker_pipe_permission_denied_is_infra():
    out = (
        "permission denied while trying to connect to the docker API at "
        "npipe:////./pipe/dockerDesktopLinuxEngine"
    )
    assert docker_deploy.looks_like_daemon_down(out) is True
    assert any(m in out for m in docker_deploy.DOCKER_INFRA_MARKERS)


# ------------------------------------------------------- D8 parseur pré-merge

def test_parse_overwritten_files_local_changes_form():
    out = (
        "error: Your local changes to the following files would be overwritten by merge:\n"
        "\trecipes.db\n"
        "\tdata/cache.db\n"
        "Please commit your changes or stash them before you merge.\n"
        "Aborting\n"
        "Merge with strategy ort failed.\n"
    )
    assert _parse_overwritten_files(out) == ["recipes.db", "data/cache.db"]


def test_parse_overwritten_files_untracked_form():
    out = (
        "error: The following untracked working tree files would be overwritten by merge:\n"
        "\trecipes.db\n"
        "Please move or remove them before you merge.\n"
        "Aborting\n"
    )
    assert _parse_overwritten_files(out) == ["recipes.db"]


def test_parse_overwritten_files_ignores_regular_conflict_output():
    out = (
        "Auto-merging recettes/service.py\n"
        "CONFLICT (content): Merge conflict in recettes/service.py\n"
        "Automatic merge failed; fix conflicts and then commit the result.\n"
    )
    assert _parse_overwritten_files(out) == []


def test_parse_overwritten_files_empty_output():
    assert _parse_overwritten_files("") == []
