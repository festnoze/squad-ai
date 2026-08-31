# Prediction Exchange - developer entry points (owner A01, WBS T1.1).
#
# Portable across Windows and POSIX. Two rules make it so:
#
#   1. Every recipe is a single `$(PY) -m <tool>` invocation. No `rm`, no `find`,
#      no `&&`, no shell built-ins, nothing that differs between cmd.exe, Git
#      Bash and sh.
#   2. The interpreter is a variable. It defaults to the checked in virtualenv
#      for the platform in use and can always be overridden:
#
#        make test PY=python
#        make test PY=/usr/bin/python3.12
#
# On Windows the venv interpreter is `.venv/Scripts/python.exe`; everywhere else
# it is `.venv/bin/python`. Forward slashes work in both, so no path separator
# translation is needed.

ifeq ($(OS),Windows_NT)
PY ?= .venv/Scripts/python.exe
else
PY ?= .venv/bin/python
endif

# Fast loop: everything except the tests that cost money or minutes.
FAST_MARKERS ?= not llm and not slow and not statistical

.DEFAULT_GOAL := help
.PHONY: help venv install test test-all test-fast lint lint-fix format format-check typecheck cov gate determinism clean

help:  ## Show this help
	@$(PY) -c "import re,sys;[print(f'  {m.group(1):<14} {m.group(2)}') for m in (re.match(r'^([a-z-]+):.*?## (.*)$$', l) for l in open('Makefile', encoding='utf-8')) if m]"

venv:  ## Create .venv with the interpreter on PATH (run once, then use install)
	python -m venv .venv

install:  ## Install the package plus the dev extra into the current interpreter
	$(PY) -m pip install -e ".[dev]"

test:  ## Run the whole suite quietly (the T1.1 exit gate)
	$(PY) -m pytest -q

test-fast:  ## Run only the tests that are cheap: no llm, no slow, no statistical
	$(PY) -m pytest -q -m "$(FAST_MARKERS)"

test-all:  ## Run everything including slow and statistical, still excluding llm
	$(PY) -m pytest -m "not llm"

determinism:  ## Run only the AC-P1 guards. Never skipped, never marked xfail.
	$(PY) -m pytest -q -m determinism

lint:  ## ruff check (no writes)
	$(PY) -m ruff check src tests

lint-fix:  ## ruff check --fix
	$(PY) -m ruff check src tests --fix

format:  ## ruff format (writes)
	$(PY) -m ruff format src tests

format-check:  ## ruff format --check (no writes, what CI runs)
	$(PY) -m ruff format --check src tests

typecheck:  ## mypy in strict mode over src/pxe
	$(PY) -m mypy

cov:  ## Coverage over the suite, terminal plus XML for the CI upload
	$(PY) -m pytest -q --cov=pxe --cov-report=term-missing --cov-report=xml

# What CI runs, in the order CI runs it. Fails on the first red step.
gate: lint format-check typecheck cov  ## lint + format check + typecheck + suite under coverage

clean:  ## Remove caches and coverage artefacts
	$(PY) -c "import shutil,pathlib;[shutil.rmtree(p, ignore_errors=True) for p in list(pathlib.Path('.').rglob('__pycache__')) + list(pathlib.Path('.').rglob('.pytest_cache')) + [pathlib.Path('.mypy_cache'), pathlib.Path('.ruff_cache'), pathlib.Path('htmlcov')]]"
	$(PY) -c "import pathlib;[p.unlink() for p in [pathlib.Path('coverage.xml'), pathlib.Path('.coverage')] if p.exists()]"
