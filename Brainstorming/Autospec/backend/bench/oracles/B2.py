"""Hidden oracle of B2 (todo_cli), derived only from bench/briefs/B2-todo-cli.md."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from bench.oracle import Check, Product


def checks(product: Product, tmp: Path) -> list[Check]:
    work = tmp / "b2"
    work.mkdir()
    counter = iter(range(1, 1000))

    def cli(*args: str, db: Path | None = None):
        argv = ["-m", "todo_cli"]
        if db is not None:
            argv += ["--db", str(db)]
        return product.run([*argv, *args], cwd=work, timeout_s=60)

    def fresh_db() -> Path:
        return work / f"t{next(counter)}.json"

    def lines(result) -> list[str]:
        return [line.rstrip() for line in result.stdout.splitlines() if line.strip()]

    def help_exits_zero():
        result = cli("--help")
        return result.returncode == 0 and bool(result.stdout.strip()), f"rc={result.returncode}"

    def add_prints_ids_from_one():
        db = fresh_db()
        first, second = cli("add", "Acheter du pain", db=db), cli("add", "Payer le loyer", db=db)
        ok = lines(first) == ["1"] and lines(second) == ["2"] and first.returncode == 0
        return ok, f"{lines(first)} {lines(second)}"

    def list_format_and_done():
        db = fresh_db()
        cli("add", "Acheter du pain", db=db)
        cli("add", "Payer le loyer", db=db)
        done = cli("done", "1", db=db)
        listing = cli("list", db=db)
        expected = ["1 [x] Acheter du pain", "2 [ ] Payer le loyer"]
        return done.returncode == 0 and lines(listing) == expected, f"{lines(listing)}"

    def remove_and_ids_never_reused():
        db = fresh_db()
        cli("add", "a", db=db)
        cli("add", "b", db=db)
        removed = cli("remove", "2", db=db)
        third = cli("add", "c", db=db)
        listing = cli("list", db=db)
        ok = removed.returncode == 0 and lines(third) == ["3"] and lines(listing) == ["1 [ ] a", "3 [ ] c"]
        return ok, f"add -> {lines(third)}, list -> {lines(listing)}"

    def title_is_trimmed():
        db = fresh_db()
        cli("add", "   Lire un livre  ", db=db)
        return lines(cli("list", db=db)) == ["1 [ ] Lire un livre"], ""

    def empty_title_exit_2():
        db = fresh_db()
        result = cli("add", "   ", db=db)
        ok = result.returncode == 2 and bool(result.stderr.strip()) and not lines(cli("list", db=db))
        return ok, f"rc={result.returncode}"

    def unknown_id_exit_1_unchanged():
        db = fresh_db()
        cli("add", "a", db=db)
        before = db.read_text(encoding="utf-8") if db.exists() else ""
        done, remove = cli("done", "42", db=db), cli("remove", "42", db=db)
        after = db.read_text(encoding="utf-8") if db.exists() else ""
        ok = done.returncode == 1 and remove.returncode == 1 and bool(done.stderr.strip()) and before == after
        return ok, f"done rc={done.returncode}, remove rc={remove.returncode}"

    def list_missing_file_is_empty():
        result = cli("list", db=work / "absent.json")
        return result.returncode == 0 and not lines(result), f"rc={result.returncode}"

    def db_is_valid_json():
        db = fresh_db()
        cli("add", "a", db=db)
        try:
            json.loads(db.read_text(encoding="utf-8"))
            return True, ""
        except (OSError, ValueError) as exc:
            return False, str(exc)

    def default_db_in_cwd():
        result = cli("add", "défaut")
        return result.returncode == 0 and (work / "todo.json").is_file(), f"rc={result.returncode}"

    tests: list[tuple[str, Callable]] = [
        ("help_exits_zero", help_exits_zero), ("add_prints_ids_from_one", add_prints_ids_from_one),
        ("list_format_and_done", list_format_and_done),
        ("remove_and_ids_never_reused", remove_and_ids_never_reused),
        ("title_is_trimmed", title_is_trimmed), ("empty_title_exit_2", empty_title_exit_2),
        ("unknown_id_exit_1_unchanged", unknown_id_exit_1_unchanged),
        ("list_missing_file_is_empty", list_missing_file_is_empty), ("db_is_valid_json", db_is_valid_json),
        ("default_db_in_cwd", default_db_in_cwd),
    ]
    results = []
    for check_id, fn in tests:
        try:
            passed, detail = fn()
        except Exception as exc:
            passed, detail = False, f"{type(exc).__name__}: {exc}"
        results.append(Check(check_id, bool(passed), "" if passed else detail))
    return results
