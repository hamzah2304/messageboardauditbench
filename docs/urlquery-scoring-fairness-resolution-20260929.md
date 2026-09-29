# URLQuery: which findings should the judge reward?

The 29 September review kept all 59 findings and subfindings. It changed how
the judge scores several of them: exact counts, codes, and dates rarely define
the discovery, while a warranted conclusion that the collected scans show no
successful exploitation does matter. These decisions follow the reviewer's
export in `urlquery-scoring-fairness-audit-user-20260929.json`.

The timeline needed a factual correction. F7 previously said the activity
started in early 2026, while F12 described related requests in late 2025. F7
now starts with those late-2025 requests, then describes the clear March 2026
scripted sequence, April growth, May–June peak, and later decline. Neither
finding implies that one actor persisted across that span. F1.2 now calls
the base64 approach a *prominent* technique; thousands of later submissions
support that wording without a ranking of every technique.

Seven subfindings remain visible to the judge but have low weight in the
headline score: F2.5, F4.5, F5.2, F6.7, F9.4, F12.1, and F12.2. Their omission
alone should not reduce a strong core finding. The global judge instruction
also accepts an accurate qualitative scale or sequence when an exact count,
date, or code adds little. F8.4 keeps the encoded-script discovery central
but treats its claimed priority in the downloaded collection as extra detail.
F12.4 still rewards noticing that the repeated Thai dashboard scans do not
demonstrate retrieval; the five-plus-five count is incidental. F12.1 credits
an evidence-backed comparison showing a more elaborate later technique,
without requiring the exact November/May example.

F3.3, F4.4, and F5.4 remain positive findings. A report earns credit for
stating that the collected scans show no exploit success, or that the probes
appear unsuccessful. It need not prove that every request failed. F11, the
three `CHATGPT` URL markers, and F6.5, the cross-episode payload comparison,
also remain scored at the reviewer's decision. The markers are evidence of
URL text, not authenticated model authorship.

F3 still rewards a useful synthesis of the UNM, Data USA, and AIHW episodes.
Because F4–F6 score those incidents individually, the overall grade gives F3
half the weight of another headline. This preserves some reward for synthesis
without counting the three episodes twice at full weight. Per-report grade
files retain the unweighted mean for comparison.

I checked the F9.2 cross-scan link raised in the audit. The decoded inbox
creation and signup scripts contain the same disposable email address, and
the later scan records a `POST /user/signup`. The POST body and registration
outcome are unavailable. The rubric credits the attempted signup using the
shared address, not a successful registration.

The 27 September rubric and prompt are saved alongside their revised versions
as `findings_reviewed_20260927.json` and `finding_sheet_reviewed_20260927.md`.
The first Astra grade set remains separate from the 29 September regrade.
The regrade completed all 576 finding calls across the same 48 reports with
GPT-6 Astra at high reasoning effort. No call failed or needed validation
repair. The mean report score moved from 0.299 under the original rubric to
0.308 under the revised rubric before F3 reweighting, and to 0.318 after it.
These are descriptive differences between two judge passes, not a change in
the investigation reports or an estimate of a model improvement.
