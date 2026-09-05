# Four-way results — recall (GPT-5.6 Sol grader) + precision

| model | recall | L1 | L2 | L3 | L4 | full/part/miss | calibration | precision | contradicted |
|---|--:|--:|--:|--:|--:|:--:|--:|:--:|--:|
| GPT-5.6 Sol | 0.47 | 0.59 | 0.34 | 0.40 | 0.60 | 20/18/24 | 0.92 | 7/10 | 2 |
| Claude Opus 5 | 0.62 | 0.78 | 0.53 | 0.60 | 0.55 | 34/9/19 | 0.92 | 5/10 | 8 |
| Claude Haiku 4.5 | 0.08 | 0.19 | 0.06 | 0.03 | 0.05 | 4/2/56 | 1.00 | 2/10 | 25 |
| GPT-5.6 Luna | 0.19 | 0.34 | 0.19 | 0.15 | 0.00 | 5/13/44 | 0.92 | 7/10 | 3 |

Notes: gpt & opus recall were graded by me (Claude) reading the full reports; haiku & luna recall by GPT-5.6 Sol via the same rubric. Precision for all four by GPT-5.6 Sol.
