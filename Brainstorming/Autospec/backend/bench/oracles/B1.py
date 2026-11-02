"""Hidden oracle of B1 (slugify_lib), derived only from bench/briefs/B1-slugify.md."""

from __future__ import annotations

import json
from pathlib import Path

from bench.oracle import Check, Product

CASES = [
    ("brief_hello_world", ["Hello, World!"], {}, "hello-world"),
    ("brief_accents_spaces", ["  Étude   de  CAS "], {}, "etude-de-cas"),
    ("brief_empty", [""], {}, ""),
    ("brief_underscore_dot", ["snake_case v2.0"], {}, "snake-case-v2-0"),
    ("brief_max_15", ["Hello beautiful world"], {"max_length": 15}, "hello-beautiful"),
    ("brief_max_12", ["Hello beautiful world"], {"max_length": 12}, "hello"),
    ("brief_long_word_cut", ["Anticonstitutionnellement"], {"max_length": 10}, "anticonsti"),
    ("cedilla_and_symbols", ["Ça coûte 5€ !"], {}, "ca-coute-5"),
    ("only_symbols", ["!!! ??? ***"], {}, ""),
    ("no_edge_dashes", ["--Déjà vu--"], {}, "deja-vu"),
    ("max_none_unchanged", ["Hello beautiful world"], {"max_length": None}, "hello-beautiful-world"),
    ("short_enough_unchanged", ["Hello beautiful world"], {"max_length": 100}, "hello-beautiful-world"),
]

_SCRIPT = """
import json, sys
from slugify_lib import slugify
out = []
for args, kwargs in json.loads(sys.stdin.read()):
    try:
        out.append(["ok", slugify(*args, **kwargs)])
    except Exception as exc:
        out.append(["error", f"{type(exc).__name__}: {exc}"])
print(json.dumps(out))
"""


def checks(product: Product, tmp: Path) -> list[Check]:
    payload = json.dumps([[args, kwargs] for _, args, kwargs, _ in CASES])
    script = tmp / "b1_oracle.py"
    script.write_text(_SCRIPT, encoding="utf-8")
    from bench import proc
    result = proc.run([product.python, str(script)], cwd=product.dir, env=product.env(),
                      input_text=payload, timeout_s=60)
    try:
        answers = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        detail = proc.tail(result.stderr or result.stdout, 400)
        return [Check(case_id, False, f"cannot call slugify: {detail}") for case_id, *_ in CASES]
    results = []
    for (case_id, args, kwargs, expected), (status, value) in zip(CASES, answers):
        passed = status == "ok" and value == expected
        results.append(Check(case_id, passed, "" if passed else f"slugify(*{args!r}, **{kwargs!r}) -> "
                             f"{value!r}, expected {expected!r}"))
    return results
