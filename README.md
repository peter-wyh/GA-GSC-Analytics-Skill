# GA-GSC Analytics Skill

Pull Google Analytics 4 + Google Search Console data with a single service account — no `google-auth`, no SDK. Pure Python stdlib with hand-signed RS256 JWTs (`openssl dgst -sha256 -sign`), plus the full methodology for wiring access, diagnosing failures, and turning raw numbers into an actionable report.

## What's inside

| Path | Purpose |
|---|---|
| `SKILL.md` | Entry point: three-gate access model, failure-signature table (403 SERVICE_DISABLED / wrong GCP project / sibling-API confusion), pitfalls |
| `scripts/ga4-probe.py` | One-shot probe: token → list properties → trial `runReport`. Run this before anything else |
| `scripts/ga-gsc-report.py` | Combined fetch pipeline: GSC (pages/queries/pairs/trend) + GA4 (sessions/events/keyEvents per page) in one JSON |
| `scripts/ga-gsc-join.py` | Page-path join + four-quadrant diagnosis (visible-no-sessions / clicks-no-conversion / sessions-no-impressions / CTR lesion) |
| `scripts/gsc-cluster.py` | Query-cluster aggregation + opportunity keywords + zero-click-at-good-position P0 list |
| `scripts/desensitize.py` | Redaction pass for publishing skills that grew private identifiers |
| `references/` | Methodology: combined-report thresholds, join recipe, publish/desensitization checklist |

## Quick start

```bash
cp config.example.json config.json   # fill in your sites + SA key paths
python3 scripts/ga4-probe.py         # verify the three access gates
python3 scripts/ga-gsc-report.py     # fetch, default site, last 28 days
python3 scripts/ga-gsc-join.py <raw.json> <host>
```

Config precedence: `CLI --site` > env (`LH_SITE` / `GA4_PROPERTY_ID` / `OUT_DIR` / `GSC_CREDS` / `GA4_CREDS`) > `config.json`.

## The three gates (read this before debugging 403s)

1. **Token** — service account + JWT, scope `analytics.readonly` (GSC: `webmasters`). Key file never enters this repo; `config.json` only points to it.
2. **API enablement** — the SA's GCP project must have *both* `analyticsadmin.googleapis.com` and `analyticsdata.googleapis.com` enabled. Deep links must carry `?project=<project-ID>` (the ID, not the numeric number) or the console silently lands on the user's default project. Classic trap: project *display names* ≠ project *ID*.
3. **Property access** — add the SA email as Viewer on the GA4 property (account-level Viewer also works).

GSC side: probe `GET webmasters/v3/sites` first — one call lists every site the SA can already access. Don't assume you need fresh authorization per site.

## Privacy model

`config.json` (real site IDs, property IDs, credential paths) and `references/private/` (dated incident logs with real business numbers) are gitignored — the public repo ships methodology and generic tooling only, zero real metrics.

## License

MIT
