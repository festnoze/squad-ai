import os
import tempfile
import unittest

from atlas.config import Engagement
from atlas.estate import pack_price, run_survey

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def make_engagement(tmp, repo_names):
    return Engagement({
        "name": "test-estate",
        "out": os.path.join(tmp, "out"),
        "work": os.path.join(tmp, "work"),
        "repos": [{"name": n, "path": os.path.join(FIXTURES, n)}
                  for n in repo_names],
    })


class PricingTests(unittest.TestCase):
    def test_pack_price_tranches(self):
        self.assertEqual(pack_price(30), 710)      # 290 + 30*14
        self.assertEqual(pack_price(200), 1890)    # 290 + 700 + 150*6
        self.assertEqual(pack_price(1000), 4065)   # + 750*2.5
        # repos beyond the 5th get the multi-repo discount
        self.assertEqual(pack_price(30, repo_index=6), round(710 * 0.85))


class EstateSurveyTests(unittest.TestCase):
    def test_survey_finds_cross_repo_coupling(self):
        with tempfile.TemporaryDirectory() as tmp:
            engagement = make_engagement(tmp, ["pyapp", "consumerapp",
                                               "reactapp", "csapp"])
            result = run_survey(engagement)
            edges = {(e["from"], e["to"]) for e in result["coupling"]}
            self.assertIn(("consumerapp", "pyapp"), edges)
            via = next(e["via"] for e in result["coupling"]
                       if e["from"] == "consumerapp" and e["to"] == "pyapp")
            self.assertIn("billingcore", via)

            self.assertEqual(result["totals"]["repos"], 4)
            self.assertEqual(result["totals"]["survey_price_eur"], 2900 + 90 * 4)
            self.assertTrue(os.path.exists(
                os.path.join(engagement.out_dir, "survey.md")))
            for repo in result["repos"]:
                self.assertIn(repo["triage"]["level"],
                              ("deep", "docs-only", "inventory"))
            pyapp = next(r for r in result["repos"] if r["repo"] == "pyapp")
            self.assertEqual(pyapp["in_degree"], 1)


class PackPipelineTests(unittest.TestCase):
    def test_full_pack_facts_only_passes_gates(self):
        import run_atlas
        with tempfile.TemporaryDirectory() as tmp:
            engagement = make_engagement(tmp, ["pyapp"])
            ok = run_atlas.build_pack(engagement, engagement.repos[0],
                                      llm_on=False)
            self.assertTrue(ok, "facts-only pack must pass its own gates")
            pack_dir = os.path.join(engagement.out_dir, "pyapp", "pack")
            for name in ("01_overview.md", "02_architecture.md",
                         "06_dependencies.md", "07_onboarding.md",
                         "08_debt_register.md", "verification_report.md"):
                self.assertTrue(os.path.exists(os.path.join(pack_dir, name)),
                                f"missing {name}")
            snaps = os.listdir(os.path.join(engagement.work_dir, "pyapp",
                                            "snapshots"))
            self.assertEqual(len(snaps), 1)


if __name__ == "__main__":
    unittest.main()
