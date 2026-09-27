# report-eval-harness

A small Inspect eval in the style of MessageBoardAuditBench (MBAB). An agent gets raw urlquery.net records in a locked-down Docker sandbox and a blind prompt ("work out what happened and why"). It writes `/work/report.md`, and an LLM judge scores the report against a hand-written answer key.

The agent is a ReAct **lead investigator** with `bash` and `text_editor`. It can also call an **analyst subagent**, which has its own shell and its own context in the same sandbox: the lead sends it one focused question and gets back only the answer. Turn the analyst off with `-T subagents=false` to get the single-agent baseline.

## Setup

```bash
uv sync                       # Python 3.13 (uv-managed), inspect-ai, anthropic, openai
cp .env.example .env          # add ANTHROPIC_AUTH_TOKEN (subscription) or ANTHROPIC_API_KEY
orb start                     # or Docker Desktop: the sandbox needs a Docker daemon
uv run report-eval-harness fetch puchoiswater   # raw records -> data/ (gitignored)
uv run pytest                 # includes a free end-to-end run with a scripted model
```

`pyproject.toml` sets `python-preference = "only-managed"` because uv's interpreter discovery hangs on the pyenv shims on this machine. If `uv` still hangs, drop pyenv from `PATH` for the command.

`sandbox/Dockerfile` builds two images, neither with setuid binaries: `tools` (stdlib Python, jq, ripgrep, sqlite3), where the corpus lives and every shell command runs, and `claude` (the Claude Code CLI, used only with `-T agent=claude_code`). Every container is locked down (`sandbox.py`):
- **Isolation:** no network, all capabilities dropped, `no-new-privileges`, uid 1000.
- **Filesystem:** the root filesystem is read-only, and the corpus is read-only at `/work/data` (see [What the agent sees](#what-the-agent-sees)). The only writable places are `/work` (a per-run volume, deleted with the run) and size-capped tmpfs for `/tmp`, `/home/agent` and `/var/tmp`.
- **Limits:** 512 pids, 4 GB of memory, 2 CPUs.

The Docker tests check the read-only mounts, the network block, the ReAct subagent round-trip, the Claude Code lockdown, and the per-tool-call feedback for both agents.

## Running

Free plumbing check (no API calls):

```bash
uv run inspect eval report_eval_harness/investigation --model mockllm/model --no-score --message-limit 6
```

A real pilot. `--model` is the lead, `subagent` is the analyst (it defaults to the lead's model), and `grader` is the judge:

```bash
uv run inspect eval report_eval_harness/investigation \
  -T time_limit_minutes=10 \
  --model anthropic/claude-sonnet-5 \
  --model-role subagent=anthropic/claude-haiku-4-5-20251001 \
  --model-role grader=anthropic/claude-fable-5-1 \
  --epochs 3
uv run inspect view           # browse transcripts, tool calls, the report and per-claim grades
```

Default judge: `anthropic/claude-fable-5-1`, as in MBAB. For the Transluce corpus, don't use an OpenAI judge, because the incident is attributed to OpenAI.

### Claude Code as the agent (subscription auth, no credential in the sandbox)

`-T agent=claude_code` runs the real Claude Code CLI via [inspect_swe](https://meridianlabs-ai.github.io/inspect_swe/claude_code.html), in a second offline container, `claude`. Claude Code's API calls go to inspect_swe's bridge in that container. The bridge relays them to Inspect on the host, which is the only process holding a credential. Claude Code sees only a dummy key.

To bill your Claude subscription rather than an API key:

```bash
claude setup-token                                  # browser login; prints a ~1-year token
echo 'ANTHROPIC_AUTH_TOKEN=sk-ant-oat01-...' >> .env # Inspect sends it as Bearer + oauth beta
uv run inspect eval report_eval_harness/investigation -T agent=claude_code \
  --model anthropic/claude-sonnet-5
```

- **Tools:** every native Claude Code tool is disallowed (`CLAUDE_CODE_DISALLOWED` in `agents.py`), including Bash, Read, Write, Edit, the web tools and subagents. Claude Code works alone with Inspect's `bash` and `text_editor`, bridged over MCP as `mcp__sandbox__bash` and `mcp__sandbox__text_editor`. They run in the `tools` container with the corpus. `-T subagents=true` is an error for this agent.
- **Nested models:** the model's commands run in a container that shares no network, filesystem or process namespace with the bridge, and that has no `claude` binary. There's no route to a second model.
- **Working directory:** the `claude` container gets an empty tmpfs `/work` as its cwd, so the directory Claude Code is told it is in matches the one its bridged shell runs in, and "report.md in this directory" lands in `/work/report.md`.
- **Binary:** Claude Code is baked into the `claude` stage of `sandbox/Dockerfile`, because the capability-dropped container can't install it at run time. Rebuild the image to change versions: `--build-arg CLAUDE_CODE_VERSION=...`.
- **Judge (untested):** while `ANTHROPIC_AUTH_TOKEN` is set, the judge also goes out on the subscription token. Subscription tokens may reject requests that don't come from Claude Code. If the judge 4xxs, point `--model-role grader=` at a non-`anthropic/` provider.

### Task options (`-T`)

| option | default | meaning |
|---|---|---|
| `corpus` | `puchoiswater` | a directory under `corpora/` |
| `agent` | `react` | `react` (Inspect ReAct loop) or `claude_code` (the Claude Code CLI) |
| `prompt` | `blind.txt` | a file in `prompts/` (see [Prompts](#prompts)); `investigation_prompt.txt` is the agent-swarm prompt |
| `effort` | model default | `claude_code` only: low/medium/high/xhigh/max |
| `subagents` | `true` for react | give the ReAct lead the `analyst` tool (not available for `claude_code`) |
| `time_limit_minutes` | `10` | wall-clock budget per sample (also stated in the prompt) |
| `report_min_words` | `2500` | lower word target stated in the prompt and in the feedback |
| `report_max_words` | `3000` | word limit stated in the prompt and in the feedback; `0` drops the `{{#REPORT_LENGTH}}` sections |
| `subagent_message_limit` | `60` | message cap per analyst call |
| `truncation` | `auto` | ReAct context truncation (`disabled` matches MBAB's bare loop) |

### Prompts

Prompts in `prompts/` use `{{NAME}}` for values and `{{#NAME}}...{{/NAME}}` for sections kept only when `NAME` is true (`prompts.py`). An unknown name or an unclosed section is an error, so a typo never reaches the model. Other braces pass through.

| name | value |
|---|---|
| `N_RECORDS` | number of scans |
| `BUDGET_MIN` | `time_limit_minutes` |
| `REPORT_MIN_WORDS`, `REPORT_MAX_WORDS` | the word limits, formatted like `2,500` |
| `REPORT_LENGTH` | section flag: true when `report_max_words` > 0 |
| `SUBAGENT_NOTE` | a line about the analyst tool when it's enabled, else empty |
| `FINISH_NOTE` | how to finish (`submit()` for ReAct); empty in the standalone runner |

### What the agent sees

The agent starts in `/work`. `/work/data` holds two files, built from `data/<name>/` into `build/data/<name>/` each time the task is created (`build_sandbox_data` in `corpus.py`):
- `scans.jsonl`: one raw urlquery record per line, sorted by scan time. Each record's `report_id` is its scan ID.
- `README.txt`: the field schema and the citation format, `[scan](https://urlquery.net/report/<report_id>)`. It describes the format only, never the content.

The report goes to `/work/report.md`.

### Feedback after each tool call

Every tool result the lead sees (ReAct's `bash`, `text_editor` and `analyst`; Claude Code's bridged `bash` and `text_editor`) ends with a harness note (`feedback.py`), as the investigation prompt promises. Tool errors carry it too.

```
[harness] Time remaining: 23m10s of 30m00s. report.md changed: 2,431 words (target 2,500-3,000); TL;DR 187 words (max 200).
```

- **Time** comes from the sample's Inspect time limit, on every call.
- **Counts** appear only when `report.md` has changed since the last note. Words are whitespace-separated units after removing complete inline links `[label](URL)`, the prompt's definition. Headings, tables and code count.
- **TL;DR** is the body under the first heading that mentions it, or after a `**TL;DR:**` lead-in, up to the next heading of any level. The heading or lead-in itself isn't counted. If there's no TL;DR, the note says so.

The analyst subagent gets no note. The scorer records the same counts as `report_words` and `tldr_words` in the score metadata.

### Scoring

`claim_judge` makes one judge call per sample. The judge scores every claim 0–1 in 0.1 steps, using anchored descriptions and MBAB's two main rules:
- the report must draw the conclusion, not just show the evidence;
- the judge searches the whole report.

It reports two numbers:
- `raw`: the plain mean of the claim scores;
- `strict`: the mean of `max(2s − 1, 0)`, so half-credit counts as zero.

If the judge's reply can't be parsed at all, the sample errors and stays unscored rather than getting 0, following MBAB's rule. Re-score it with `inspect score`.

## Web UI

```bash
uv run report-eval-harness web      # http://127.0.0.1:8765, Inspect View on :8766
```

A small launcher over the same `inspect eval` runs as the CLI:
- **Start a run:** pick the agent (Claude Code or ReAct), corpus, prompt, models, time limit, epochs and report length. You can also edit the prompt; an edited prompt runs as a copy in `prompts/.webui/` (gitignored), and template errors are rejected before launch.
- **Read a run:** each run shows its status, strict and raw scores, tokens and elapsed time, plus tabs for the rendered report, per-claim grades (per epoch), the live console, the exact prompt and the config.
- **Transcripts:** open in Inspect View, which this server starts. It refuses to be framed, so it opens in a new tab.
- **Stop:** sends SIGINT, so Inspect writes a `cancelled` log and tears the containers down.
- **Bookkeeping:** runs are tagged with eval metadata `webui_run=<id>`. The console output and launch record live in `build/webui/`. Runs started from the CLI into `logs/` show up too.
- **No credentials?** `mockllm/model` works for a free plumbing check.

## Layout

```
corpora/<name>/ids.txt            urlquery report IDs (committed)
corpora/<name>/answer_key.jsonl   claims: id, section, claim, grading_mode, note (committed)
corpora/<name>/SHA256SUMS         checksums of fetched records (committed, written on first verify)
data/<name>/                      raw records (gitignored; urlquery forbids redistribution)
build/data/<name>/                scans.jsonl + README.txt mounted at /work/data (gitignored)
prompts/*.txt                     task prompts (blind.txt, investigation_prompt.txt); analyst.txt
sandbox/Dockerfile                images: `tools` (data + shell) and `claude` (Claude Code CLI)
src/report_eval_harness/          task.py, agents.py, feedback.py, prompts.py, scorer.py,
                                  corpus.py, sandbox.py, web.py + static/index.html
```

## Corpora

- **`puchoiswater`**: a 22-record smoke corpus with a known answer. It is a November 2023 Microsoft 365 phishing kit that uses adversary-in-the-middle proxying of the real login page. Six of its records sit in Transluce's catalogue as `review_required`. The answer key has 7 claims; see `../hugo-notes/transluce-urlquery-puchoiswater.md`.

To add a corpus (for example, one Transluce episode), create `corpora/<name>/ids.txt` and `answer_key.jsonl`, then `fetch` it.

## Known gaps (vs MBAB)

- **No redaction yet.** The raw records contain victims' email addresses (puchoiswater) and live-looking tokens (Transluce June chain), and they are sent to the model provider as-is. Add a redacting builder before anything larger.
- **The corpus is the full raw urlquery JSON**, one record per line, not a slimmed projection. That's fine at 7 MB, but not at 38k records, and `scans.jsonl` is rebuilt every time the task is created.
- **Feedback, but no enforcement.** The agent is told the time remaining and the report counts after each tool call. There's still no minimum-runtime rule (MBAB sends an agent back to work if it stops before 75% of the budget) and no "shorten it" turn for an over-long report. A report is graded as it stands when the time limit hits.
- **No holistic TL;DR sheet**, so there is no 70/30 headline score. Contamination baselines (a no-data run and a perturbed variant) are not built yet.
