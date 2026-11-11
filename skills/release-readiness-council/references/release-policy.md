# Release policy (policy as code)

The policy lives in `release.json` under `policy`. Teams should version it and change it through review, not per release.

| Field | Default | Meaning |
| --- | --- | --- |
| `required_specialists` | quality, security, performance, customer-risk | Missing any of these returns `INCOMPLETE` |
| `hold_on_blocking_severity` | `high` | Any supported blocking finding at or above this recommends HOLD |
| `max_high_findings_for_go` | `1` | More supported high or critical findings than this recommends HOLD |
| `area_owners` | area to specialist map | Used to detect a specialist saying GO while another holds a blocking finding in its area |
| `release_path_controls` | `["gh.main."]` | Tripwire control id prefixes that guard this release path |

## Decision order

1. Missing required specialist: `INCOMPLETE`
2. Supported blocking finding at or above threshold: `RECOMMEND_HOLD`
3. Too many high findings: `RECOMMEND_HOLD`
4. Any conditions or GO_WITH_CONDITIONS: `RECOMMEND_GO_WITH_CONDITIONS`
5. Otherwise: `RECOMMEND_GO`

## Risk acceptance

The release owner may ship over a HOLD recommendation. When they do, the decision record must name each accepted risk, its owner and an expiry date. The council never records acceptance on anyone's behalf.
