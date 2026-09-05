# hasan/

Shared UIs and validation artifacts.

- **validation.html** — manual validation UI for the rubric grading. Shows each of the
  68 claims one at a time: the verified dump reference, the matching passage from the
  human report, and the best-matching passage from each model report (GPT-5.6 Sol,
  Claude Opus 5) with keyword highlighting. Score each model miss/partial/full
  (red/yellow/green), add per-model notes, navigate with left/right, and Save JSON.
  Buttons are pre-loaded with the auto-grader's scores; clicking marks a verdict
  as human-validated. Work autosaves to the browser (localStorage).
- **validation_data.json** — the claims + extracted passages the UI is built from.

Open validation.html via the html-viewer (http://localhost:8765/).
