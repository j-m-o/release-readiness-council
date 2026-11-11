"""Scenario tests for Release Readiness Council. Run: python -m unittest discover tests"""
import copy
import json
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "release-readiness-council"
sys.path.insert(0, str(SKILL / "scripts"))
import council  # noqa: E402

REL = SKILL / "assets" / "fixtures" / "release-4.2"


def load_all():
    release = json.loads((REL / "release.json").read_text())
    ops = [json.loads(f.read_text()) for f in sorted((REL / "opinions").glob("*.json"))]
    ops.append(council.from_flaky(json.loads((REL / "flaky-report.json").read_text())))
    ops.append(council.from_tripwire(json.loads((REL / "tripwire-report.json").read_text()), release["policy"]["release_path_controls"]))
    return release, ops


class ConflictingCouncil(unittest.TestCase):
    def setUp(self):
        self.release, self.ops = load_all()
        self.r = council.deliberate(self.release, self.ops)

    def test_recommends_hold_and_never_decides(self):
        self.assertEqual(self.r["council_recommendation"], "RECOMMEND_HOLD")
        self.assertEqual(self.r["decision"]["status"], "AWAITING_RELEASE_OWNER")

    def test_subagent_and_agent_evidence_flow_into_blocking_findings(self):
        ids = {f["id"] for f in self.r["blocking_findings"]}
        self.assertIn("FLAKY-T-101", ids)
        self.assertIn("TRIP-gh.main.required_status_checks", ids)
        self.assertIn("S-1", ids)

    def test_split_and_contradiction_are_surfaced_not_averaged(self):
        self.assertTrue(any("GO:" in c["between"][0] for c in self.r["conflicts"]))
        self.assertTrue(any(c["between"] == ["quality-reviewer", "flaky-test-investigator"] for c in self.r["conflicts"]))

    def test_claims_without_evidence_are_excluded(self):
        self.assertEqual(len(self.r["unsupported_claims"]), 1)
        self.assertEqual(self.r["unsupported_claims"][0]["specialist"], "customer-risk-reviewer")

    def test_unknowns_from_subagent_are_kept(self):
        self.assertTrue(any("T-108" in u for u in self.r["unknowns"]))


class Policy(unittest.TestCase):
    def test_missing_required_specialist_is_incomplete(self):
        release, ops = load_all()
        ops = [o for o in ops if o["specialist"] != "security-reviewer"]
        self.assertEqual(council.deliberate(release, ops)["council_recommendation"], "INCOMPLETE")

    def test_clean_release_with_conditions(self):
        release, ops = load_all()
        clean = []
        for o in ops:
            if o["kind"] != "specialist":
                continue
            o = copy.deepcopy(o)
            o["findings"] = [f for f in o["findings"] if not f.get("blocking")]
            o["recommendation"] = "GO_WITH_CONDITIONS" if o["conditions"] else "GO"
            clean.append(o)
        self.assertEqual(council.deliberate(release, clean)["council_recommendation"], "RECOMMEND_GO_WITH_CONDITIONS")

    def test_blocking_finding_without_evidence_cannot_force_hold(self):
        release, ops = load_all()
        ops = [o for o in ops if o["kind"] == "specialist"]
        for o in ops:
            o["findings"] = [dict(f, blocking=False) for f in o["findings"]]
            o["recommendation"] = "GO"
            o["conditions"] = []
        ops[0]["findings"].append({"id": "X", "severity": "critical", "blocking": True, "area": "quality", "claim": "Feels risky.", "evidence": []})
        r = council.deliberate(release, ops)
        self.assertEqual(r["council_recommendation"], "RECOMMEND_GO")
        self.assertIn("X", [c.get("id") for c in r["unsupported_claims"]])


if __name__ == "__main__":
    unittest.main()
