# report-browser

A local browser for the Transluce urlquery catalogue (`data/urlquery-agent-activity-2026-09-22-v5/`) and the raw urlquery records behind it. Stdlib Python, no install.

```bash
python3 report-browser/server.py                  # http://127.0.0.1:8765
python3 report-browser/server.py fetch --all      # cache every raw record (~38k, ~2 h at 5/s, resumable)
python3 report-browser/server.py fetch --confidence significant
python3 report-browser/server.py fetch --source AIHW --limit 500
python3 report-browser/server.py reindex          # rebuild data/browser.sqlite from CSVs + cached JSON
```

The catalogue alone gives only IDs, times and Transluce's labels. Anything about URLs, payloads, hosts or scripts needs the raw record. You can fetch a record by opening it, fetch a whole slice with **Reports → Fetch raw for slice…** (or the banner on the Sites tab), or run the CLI. Raw JSON, script sources and domain-graph GIFs are cached under `data/raw/`, which is gitignored: urlquery's terms forbid redistribution. The 22 puchoiswater records in `report-eval-harness/data/` are picked up automatically.

## Views

- **Timeline**: daily, hourly, weekly or monthly counts, stacked by any dimension. Click a bar to slice to it. Golden incidents show as shaded bands. Below it is a UTC hour × weekday operating clock.
- **Groups**: group by any dimension, optionally cross-tabulated by a second one. Dimensions include data source, class, carrier host, payload target host, HTTP-contacted host, script md5, and payload program signature (a hash of the decoded program with its literals abstracted away, so near-identical programs bunch together). Click a group to slice to it.
- **Bursts**: sessions split wherever the gap between reports exceeds N minutes.
- **Sites graph**: carrier (submitted host) → payload target and/or HTTP-contacted hosts, drawn with Cytoscape, plus a hosts × time heatmap.
- **Reports**: a paged table with multi-select.
- **Report drawer**: the catalogue labels, the decoded payload (recursively unwrapped base64 paths, `data:` URLs, base64 query values, nested URLs and inline `<script>` bodies), HTTP transactions with raw request and response headers, recorded scripts with their source (fetched from urlquery on demand), urlquery's Graphviz domain graph, and the raw JSON. Keys: `j`/`k` next/prev, `a` add to the current finding, `Esc` close.

Record content is only ever rendered as text. Nothing from a record is executed or inserted as HTML.

## Golden findings

Findings are grouped under incidents (e.g. "AIHW dashboard escalation, June 2026"). Each finding has a claim, section, grading mode, grading note, confidence, and evidence reports with per-report notes. Pick a finding in the header's **Annotating** menu, then add reports from the drawer (`a`) or from the table selection.

They are stored in `report-browser/golden/findings.json`. That file holds IDs and claims only, so it is safe to commit. **Write eval corpus** exports an incident to `report-eval-harness/corpora/<slug>/{answer_key.jsonl,ids.txt}` in the harness's format.
