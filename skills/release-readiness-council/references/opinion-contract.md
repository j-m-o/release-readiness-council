# Specialist opinion contract

Every specialist returns exactly this shape. The chair rejects opinions that do not parse.

```json
{
  "specialist": "security-reviewer",
  "kind": "specialist",
  "recommendation": "GO | GO_WITH_CONDITIONS | HOLD",
  "confidence": "High | Medium | Low",
  "findings": [
    {
      "id": "S-1",
      "severity": "low | medium | high | critical",
      "blocking": true,
      "area": "quality | security | performance | customer | control-integrity",
      "claim": "One sentence stating what is true.",
      "evidence": ["source:identifier", "pr:#812 diff lines 40-66"]
    }
  ],
  "claims": [
    {"claim": "Optional broader statements. Also need evidence or they are excluded.", "evidence": []}
  ],
  "conditions": ["Things that must be true if the release ships, phrased so someone can verify them."],
  "unknowns": ["What the specialist could not verify and why."]
}
```

## Rules

- `evidence` must point at something a person can open: a run, a scan finding, a diff, a dashboard, a report. Opinions are not evidence.
- `blocking: true` means: if this is true, the specialist would not ship. Use it sparingly and honestly.
- `confidence` describes the evidence, not the specialist's certainty about its own reasoning.
- Unknowns are findings. A specialist that could not check something says so instead of assuming it is fine.
