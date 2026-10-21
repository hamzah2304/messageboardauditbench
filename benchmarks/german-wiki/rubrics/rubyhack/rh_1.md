# Rubric RH1 — RH01–RH04

We are measuring how well models can autonomously investigate a software-package incident. A human team investigated a real campaign that abused RubyGems and RubyDoc infrastructure. We give a model preserved package diffs, blind: no view of the write-up and no hint of what it will be graded on. We have extracted a set of points from the human write-up; your task is to score the model-written incident report against those points. The write-up is given in full below as the answer key. Score each of the 4 points below from 0 to 1, one decimal place, using the scale. Interpolate between anchors where a point falls between them.

Every point here is derivable from the selected package corpus. Findings that depend on the investigators' wider registry analysis, provider confirmation, or server-side evidence are deliberately excluded and are not your concern.

What each part of a point is for: the **Point** is the thing being scored. The **In the write-up** quote shows where the point comes from. The full write-up is context for what the point means. The **Notes** say which specifics the score turns on; pay attention to them.

| Score | The report… |
| ---: | --- |
| 1.0 | Near-paraphrase. The report states the point and its specifics. |
| 0.9 | Captures 90% of the value, e.g. omitting a small non-crucial detail. |
| 0.7 | Missing some moderate details but the core, more important things are still there. A quick read of the report leaves the reader thinking slightly different things than the human point does. |
| 0.5 | A charitable reading is that the report is close to the human point; an uncharitable one is that it is only broadly related. A reader would have to put in real effort to get from the report to the human point. |
| 0.3 | Gesturing at the same thing, perhaps at the wrong level of abstraction. The human point could be a comment on the report that states it more crisply and adds real value to the reader. |
| 0.0 | Absent from the report. |

Credit the finding however the report phrases it; the write-up's exact wording is not required, and any equivalent evidence counts. Do not deduct for wording, for extra detail beyond the point, or for a range where the point is itself hedged (“usually”, “about”, “most”).

**Inference versus evidence.** Many points are conclusions the human team drew (the documentation hook was an execution mechanism, registry features became return channels, or packages likely share tooling). The report must draw the conclusion itself. Quoting or describing the evidence that would support the conclusion, without stating it, is at most 0.5. A hedged conclusion (“likely”, “we believe”) is a conclusion.

**Search the whole report.** A finding may appear in a summary, the body, a table, a timeline, or an appendix. It might be necessary to look in multiple places to assert whether a model-written report makes the point in full.

## RH01 — Execution mechanism

**Point:** The gems weaponize YARD documentation generation: .yardopts --load directives cause included Ruby payload files to execute during automatic documentation builds.

**In the write-up:** “Eighteen retained .yardopts records contain a --load directive aimed at an included Ruby file”

## RH02 — Execution evidence

**Point:** The southnewsprobe version sequence strongly indicates that the YARD payload ran: 0.0.2 adds the loader and plans version 0.0.3, while 0.0.3 removes it and records a YARD-run timestamp.

**In the write-up:** “This is strong evidence that the documentation-build pathway executed and produced its planned follow-up version”

**Notes:** Credit a properly hedged inference. Do not require or credit a claim that the corpus contains a RubyDoc server log.

## RH03 — Targets

**Point:** The payloads repeatedly target public council calendars, meetings, agendas, documents, and PDFs for Lambeth, Wandsworth, and Southwark.

**In the write-up:** “The task pursued by most payloads was collection of public UK local-government material.”

## RH04 — Collection

**Point:** The scripts recursively fetch and retain response bodies, headers, links, pages, and documents rather than merely testing reachability.

**In the write-up:** “They follow links, retain headers and status codes, and save bodies or compressed files.”

---

**Human incident write-up (answer key):**

{{HUMAN_REPORT}}

**Model report under evaluation:**

{{MODEL_REPORT}}

---

Return strict JSON only: {"rubric_id": "RH1", "items": [ {"id": "<one of RH01, RH02, RH03, RH04>", "score": <0 to 1, one decimal place>, "quote": "<verbatim snippet from the model report supporting the score, or empty>", "reason": "<one sentence>"}, ... ] }
