# Prompt for ChatGPT (attach methodology_v3.png)

Redraw the attached sketch as a polished, minimal methodology diagram for a research blog post. The sketch fixes the LAYOUT, CONTENT and COLOUR ROLES exactly; your job is to render it with a clean, warm, editorial illustration style. Wide format, roughly 17:7, high resolution.

CONTEXT (so the picture makes sense)
We built a benchmark. A real incident happened on a public wiki called DSEWiki: thousands of AI agents used it as a message board and colluded. The wiki's edit logs are public. Human investigators wrote an incident report from those logs. We turned that report into 30 ground-truth claims, then gave the same logs to an AI agent running in a coding-agent harness (a terminal with tools, no internet, a time limit) with the one-word prompt "Investigate." The agent writes its own report. We grade how many of the 30 human claims the agent's report recovers. That fraction is recall.

STYLE
- Look of a modern AI-lab research site: generous whitespace, thin dark line-work, rounded rectangles, a humanist sans-serif (Inter or similar). Flat. No gradients, no shadows, no 3D, no decorative background shapes, no emoji.
- Background off-white (#f7f6f2). Line-work and text near-black (#1a1a1a). Secondary text mid grey.
- Exactly two tints, each with a meaning:
  - light green (#dcebd8 fill, #3f7d4e outline) = anything HUMAN: the person icon, the highlighted passages in the human report, the claim chips.
  - light blue (#dfe4f3 fill, #1f3a93 outline) = anything AGENT: the robot, the highlighted passages in the agent report.
- Nothing else is coloured.
- All text must be real, legible, correctly spelled. Keep every label from the sketch, add none.

LAYOUT (follow the sketch)
Left edge: a stack of three overlapping document sheets labelled "DSEWiki edit logs". Two thin arrows leave it, one to each card on the right.

Card 1 (top), numbered 1, title "Human investigation":
a simple green person icon → arrow → a report page with three green-highlighted passages → thin green lines connecting each passage to a green rounded chip on the right (three chips). Labels under: "HUMAN REPORT" and "30 CLAIMS, EXTRACTED BY HAND". Small grey caption at far right: "Each claim is re-checked against the logs."

Card 2 (bottom), numbered 2, title "Agent investigation":
a speech bubble containing the word "Investigate." labelled "PROMPT" → arrow → the robot: a line-drawn robot head in deep blue with a rounded rectangular face, two round eyes, a small antenna, wearing a detective's deerstalker cap and holding a magnifying glass. Iconic and geometric, not cute. Under the robot, two small rounded badges with "> _" and ".py" labelled "TOOLS". Then an arrow → a report page with blue-highlighted passages, labelled "AGENT REPORT". Small grey caption: "Written from the logs alone." Card footer label: "CODING-AGENT HARNESS · NO INTERNET · TIME LIMIT".

Right of a thin dotted vertical rule, numbered 3, title "Grade", subtitle "Which claims does the agent recover?":
three green claim chips in a column on the left, the blue agent report page on the right. Dashed curved connectors from the first two chips to highlighted passages on the page, each with a small circled tick at the midpoint. The third chip has a small circled cross next to it and no connector (a missed claim). Labels under: "HUMAN CLAIMS" and "AGENT REPORT". Footer line: "claims recovered → recall".

No title on the image, no legend, no watermark, no outer border.
