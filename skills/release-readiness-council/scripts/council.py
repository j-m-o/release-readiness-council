#!/usr/bin/env python3
"""Release Readiness Council: aggregate specialist reviews into a decision brief.

Reads independent specialist opinions plus optional subagent reports
(Flaky Test Investigator, Control-Plane Tripwire), enforces the evidence rule,
surfaces disagreements instead of averaging them away, applies release policy,
and produces a recommendation and a decision record for a named human owner.

The council recommends. It never approves or ships.

Read-only. Standard library only. No network access.

Release Readiness Council, created by Jessica Mosley | LinkedIn: https://www.linkedin.com/in/jessmosley/ | GitHub: https://github.com/j-m-o/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RANK = {"GO": 0, "GO_WITH_CONDITIONS": 1, "HOLD": 2}
SEV = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def from_flaky(report: dict) -> dict:
    """Translate the Flaky Test Investigator contract into a council opinion."""
    findings, unknowns = [], []
    for r in report["results"]:
        if r["real_regression"]:
            findings.append({"id": f"FLAKY-{r['test_id']}", "severity": "high", "blocking": True, "area": "quality",
                             "claim": f"Real regression in '{r['name']}' from commit {r.get('first_failing_commit')}.",
                             "evidence": [f"flaky-test-investigator:{r['test_id']}"] + r["evidence"]})
        elif r["classification"] in {"INSUFFICIENT_EVIDENCE", "UNCLASSIFIED"}:
            unknowns.append(f"{r['test_id']} ({r['name']}): {r['classification']}")
    return {"specialist": "flaky-test-investigator", "kind": "subagent",
            "recommendation": "HOLD" if findings else "GO", "confidence": "High" if findings else "Medium",
            "findings": findings, "conditions": [], "unknowns": unknowns}


def from_tripwire(report: dict, release_path: list[str]) -> dict:
    """Translate a Control-Plane Tripwire report into a council opinion."""
    findings, unknowns = [], []
    if report.get("status") == "POLICY_INTEGRITY_FAILURE":
        unknowns.append("Tripwire policy integrity failure: control integrity is unverified.")
    for r in report.get("results", []):
        on_path = any(r["control_id"].startswith(p) for p in release_path)
        if r["tamper"] and on_path:
            findings.append({"id": f"TRIP-{r['control_id']}", "severity": "critical", "blocking": True, "area": "control-integrity",
                             "claim": f"{r['verdict']} on release-path control {r['control_id']}: {r['rationale']}",
                             "evidence": [f"control-plane-tripwire:{r['control_id']}", f"baseline={json.dumps(r['baseline'])}", f"current={json.dumps(r['current'])}"]})
        elif r["verdict"] == "UNVERIFIABLE" and on_path:
            unknowns.append(f"Control {r['control_id']} could not be verified.")
    return {"specialist": "control-plane-tripwire", "kind": "agent",
            "recommendation": "HOLD" if findings else "GO", "confidence": "High",
            "findings": findings, "conditions": [], "unknowns": unknowns}


def deliberate(release: dict, opinions: list[dict]) -> dict:
    policy = release["policy"]
    unsupported, supported = [], []
    for o in opinions:
        for f in o.get("findings", []):
            f = dict(f, specialist=o["specialist"])
            (supported if f.get("evidence") else unsupported).append(f)
        for c in o.get("claims", []):
            if not c.get("evidence"):
                unsupported.append(dict(c, specialist=o["specialist"], severity="n/a", blocking=False))

    present = {o["specialist"] for o in opinions}
    missing = [s for s in policy["required_specialists"] if s not in present]

    positions = {o["specialist"]: o["recommendation"] for o in opinions}
    conflicts = []
    go = sorted(k for k, v in positions.items() if v == "GO")
    hold = sorted(k for k, v in positions.items() if v == "HOLD")
    if go and hold:
        conflicts.append({"between": ["GO: " + ", ".join(go), "HOLD: " + ", ".join(hold)], "positions": ["GO", "HOLD"],
                          "resolve_by": "Split decision. The release owner weighs the cited evidence; the council does not average positions."})
    # A specialist saying GO while another's supported blocking finding is in its own area is a direct contradiction.
    area_owner = policy.get("area_owners", {})
    for f in supported:
        owner = area_owner.get(f.get("area"))
        if f.get("blocking") and owner and owner != f["specialist"] and positions.get(owner) == "GO":
            conflicts.append({"between": [owner, f["specialist"]], "positions": ["GO", f"blocking finding {f['id']}"],
                              "resolve_by": f"{owner} should review {f['id']} evidence before its GO stands."})

    blocking = [f for f in supported if f.get("blocking")]
    critical = [f for f in blocking if SEV[f["severity"]] >= SEV[policy["hold_on_blocking_severity"]]]
    highs = [f for f in supported if SEV[f["severity"]] >= SEV["high"]]
    conditions = [c for o in opinions for c in o.get("conditions", [])]
    unknowns = [u for o in opinions for u in o.get("unknowns", [])]

    reasons = []
    if missing:
        rec = "INCOMPLETE"
        reasons.append(f"Required specialist review missing: {', '.join(missing)}. Missing is not GO.")
    elif critical:
        rec = "RECOMMEND_HOLD"
        reasons.append(f"{len(critical)} supported blocking finding(s) at or above '{policy['hold_on_blocking_severity']}'.")
    elif len(highs) > policy["max_high_findings_for_go"]:
        rec = "RECOMMEND_HOLD"
        reasons.append(f"{len(highs)} high findings exceed policy limit of {policy['max_high_findings_for_go']}.")
    elif conditions or any(v == "GO_WITH_CONDITIONS" for v in positions.values()):
        rec = "RECOMMEND_GO_WITH_CONDITIONS"
        reasons.append("No blocking findings; conditions must be met and owned.")
    else:
        rec = "RECOMMEND_GO"
        reasons.append("No blocking findings and all required specialists recommend GO.")
    if unsupported:
        reasons.append(f"{len(unsupported)} claim(s) excluded for lacking evidence.")

    return {
        "release": release["id"], "title": release["title"], "release_owner": release["release_owner"],
        "council_recommendation": rec, "reasons": reasons, "positions": positions,
        "conflicts": conflicts, "blocking_findings": blocking, "other_findings": [f for f in supported if not f.get("blocking")],
        "unsupported_claims": unsupported, "conditions": conditions, "unknowns": unknowns, "missing_specialists": missing,
        "decision": {"status": "AWAITING_RELEASE_OWNER", "owner": release["release_owner"]},
    }


def brief(r: dict) -> str:
    L = [f"# Release Readiness Brief: {r['release']}", "", f"**{r['title']}**", "",
         f"**Council recommendation:** {r['council_recommendation']}  ",
         f"**Decision owner:** {r['release_owner']} (status: {r['decision']['status']})", "", "## Why"]
    L += [f"- {x}" for x in r["reasons"]]
    L += ["", "## Positions", "", "| Specialist | Position |", "| --- | --- |"]
    L += [f"| {k} | {v} |" for k, v in sorted(r["positions"].items())]
    L += ["", "## Where the council disagrees", ""]
    L += [f"- **{' vs '.join(c['between'])}** ({' / '.join(c['positions'])}). {c['resolve_by']}" for c in r["conflicts"]] or ["- No material disagreement."]
    L += ["", "## Blocking findings", ""]
    for f in sorted(r["blocking_findings"], key=lambda x: -SEV[x["severity"]]):
        L.append(f"- **[{f['severity']}] {f['id']}** ({f['specialist']}): {f['claim']}  ")
        L.append(f"  Evidence: {'; '.join(f['evidence'])}")
    if not r["blocking_findings"]:
        L.append("- None")
    L += ["", "## Conditions if shipped", ""] + ([f"- {c}" for c in r["conditions"]] or ["- None"])
    L += ["", "## Unknowns", ""] + ([f"- {u}" for u in r["unknowns"]] or ["- None"])
    L += ["", "## Excluded: claims without evidence", ""]
    L += [f"- {c['specialist']}: \"{c['claim']}\"" for c in r["unsupported_claims"]] or ["- None"]
    L += ["", "---", "", "## Decision record (completed by the release owner, not the council)", "",
          f"- Decision owner: {r['release_owner']}", "- Decision: GO / GO WITH CONDITIONS / HOLD", "- Risks accepted, with owner and expiry:",
          "- Conditions and who verifies them:", "- Date and signature:", ""]
    return "\n".join(L)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("release_dir", type=Path, help="Folder with release.json, opinions/*.json and optional subagent reports")
    p.add_argument("--format", choices=["json", "markdown"], default="markdown")
    a = p.parse_args()
    release = load(a.release_dir / "release.json")
    opinions = [load(f) for f in sorted((a.release_dir / "opinions").glob("*.json"))]
    if (a.release_dir / "flaky-report.json").exists():
        opinions.append(from_flaky(load(a.release_dir / "flaky-report.json")))
    if (a.release_dir / "tripwire-report.json").exists():
        opinions.append(from_tripwire(load(a.release_dir / "tripwire-report.json"), release["policy"].get("release_path_controls", [])))
    result = deliberate(release, opinions)
    print(json.dumps(result, indent=2) if a.format == "json" else brief(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
