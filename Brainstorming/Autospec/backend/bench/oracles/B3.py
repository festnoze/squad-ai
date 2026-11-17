"""Hidden oracle of B3 (notes_api), derived only from bench/briefs/B3-notes-api.md."""

from __future__ import annotations

from pathlib import Path

from bench.oracle import Check, Product, Server


def checks(product: Product, tmp: Path) -> list[Check]:
    db = tmp / "notes-oracle.db"
    results: list[Check] = []

    def record(check_id: str, passed: bool, detail: str = "") -> None:
        results.append(Check(check_id, bool(passed), "" if passed else detail))

    try:
        with Server(product, extra_env={"NOTES_DB": str(db)}) as api:
            status, body = api.request("GET", "/health")
            record("health", status == 200 and body == {"status": "ok"}, f"{status} {body}")

            status, first = api.request("POST", "/notes", {"title": "Courses", "body": "lait, pain"})
            shape = isinstance(first, dict) and {"id", "title", "body", "created_at"} <= set(first)
            record("create_201", status == 201 and shape and first.get("title") == "Courses",
                   f"{status} {first}")
            first_id = first.get("id") if isinstance(first, dict) else None

            status, second = api.request("POST", "/notes", {"title": "Réunion"})
            record("body_defaults_to_empty", status == 201 and isinstance(second, dict)
                   and second.get("body") == "", f"{status} {second}")
            second_id = second.get("id") if isinstance(second, dict) else None

            status, listing = api.request("GET", "/notes")
            ids = [n.get("id") for n in listing if isinstance(n, dict)] if isinstance(listing, list) else []
            record("list_sorted_by_id", status == 200 and len(ids) == 2 and ids == sorted(ids, key=str),
                   f"{status} {ids}")

            status, got = api.request("GET", f"/notes/{first_id}")
            record("get_200", status == 200 and isinstance(got, dict) and got.get("body") == "lait, pain",
                   f"{status} {got}")
            status, _ = api.request("GET", "/notes/999999")
            record("get_missing_404", status == 404, f"{status}")

            status, _ = api.request("POST", "/notes", {"title": "", "body": "x"})
            record("empty_title_422", status == 422, f"{status}")
            status, _ = api.request("POST", "/notes", {"title": "x" * 121})
            record("title_121_chars_422", status == 422, f"{status}")
            status, _ = api.request("POST", "/notes", {"title": "y" * 120})
            record("title_120_chars_ok", status == 201, f"{status}")

            status, updated = api.request("PUT", f"/notes/{first_id}", {"title": "Courses bio", "body": "œufs"})
            same = isinstance(updated, dict) and isinstance(first, dict) \
                and updated.get("id") == first_id and updated.get("created_at") == first.get("created_at")
            record("put_keeps_id_and_created_at", status == 200 and same
                   and updated.get("title") == "Courses bio", f"{status} {updated}")
            status, _ = api.request("PUT", "/notes/999999", {"title": "z"})
            record("put_missing_404", status == 404, f"{status}")

            status, found = api.request("GET", "/notes?q=COURSES")
            found_ids = [n.get("id") for n in found] if isinstance(found, list) else None
            record("search_case_insensitive", status == 200 and found_ids == [first_id], f"{status} {found_ids}")

            status, _ = api.request("DELETE", f"/notes/{second_id}")
            status_after, _ = api.request("GET", f"/notes/{second_id}")
            record("delete_204_then_404", status == 204 and status_after == 404, f"{status} then {status_after}")
            status, _ = api.request("DELETE", "/notes/999999")
            record("delete_missing_404", status == 404, f"{status}")

        with Server(product, extra_env={"NOTES_DB": str(db)}) as api:
            status, got = api.request("GET", f"/notes/{first_id}")
            record("persists_across_restart", status == 200 and isinstance(got, dict)
                   and got.get("title") == "Courses bio", f"{status} {got}")
    except RuntimeError as exc:
        results.append(Check("server_starts", False, str(exc)))
    return results
