import json

from bench.report import build


def _result(root, day, config, project, n, **overrides):
    data = {"date": day, "config": config, "project": project, "model": "sonnet", "git_sha": "abc1234",
            "m1_completed": True, "m2_duration_s": 120.0, "m3_cost_usd": 0.5, "m4_agent_calls": 6,
            "oracle": {"m5_suite": {"green": True, "passed": 10, "failed": 0},
                       "m6_oracle": {"passed": 9, "total": 10, "rate": 0.9, "checks": []},
                       "m7_smoke": {"ok": True, "detail": ""}}}
    data.update(overrides)
    folder = root / day / config
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{project}-{n}.json").write_text(json.dumps(data), encoding="utf-8")


def test_one_table_per_date_newest_first(tmp_path):
    _result(tmp_path, "2026-11-01", "c", "B1", 1)
    _result(tmp_path, "2026-11-02", "b", "B1", 1, m1_completed=False, oracle=None)
    _result(tmp_path, "2026-11-02", "c", "B2", 1)

    text = build(tmp_path)

    assert text.index("## 2026-11-02") < text.index("## 2026-11-01")
    assert "| B1 | B harness nu | sonnet | non |" in text
    assert "| B2 | C v2 | sonnet | oui | 2.0 min | 0.50 $ | 6 | 10/10 vert | 9/10 | oui | abc1234 |" in text


def test_oracle_only_rows_show_not_applicable_completion(tmp_path):
    _result(tmp_path, "2026-11-02", "v1-legacy", "B2", 1, m1_completed=None, m2_duration_s=None,
            m3_cost_usd=None, m4_agent_calls=None)

    assert "| B2 | v1-legacy | sonnet | n/a |  |  |  |" in build(tmp_path)


def test_rows_with_not_automated_criteria_show_their_count(tmp_path):
    checks = [{"id": "SEC-01", "passed": True, "detail": ""},
              {"id": "UX-01", "passed": False, "detail": "NOT_AUTOMATED"},
              {"id": "UX-02", "passed": False, "detail": "NOT_AUTOMATED"}]
    oracle = {"m5_suite": {"green": True, "passed": 3, "failed": 0},
              "m6_oracle": {"passed": 1, "total": 3, "rate": 0.333, "checks": checks},
              "m7_smoke": {"ok": True, "detail": ""}}
    _result(tmp_path, "2026-11-03", "c", "B5", 1, oracle=oracle)
    _result(tmp_path, "2026-11-03", "c", "B4", 1)

    text = build(tmp_path)

    assert "| 3/3 vert | 1/3 (2 NOT_AUTOMATED) | oui |" in text
    assert "| 10/10 vert | 9/10 | oui |" in text
