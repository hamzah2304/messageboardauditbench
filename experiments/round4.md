# Round 4 launch plan

Round 4 is a fresh blind evaluation using `blind-v2`, the verbatim dataset,
xhigh effort, and three replicates at 10, 30, and 120 minutes. Claude Code and
Codex use subscription credentials. ReAct runs natively through Inspect and
OpenRouter. Generation is deliberately unscored; grading happens afterward.

The manifest declares 118 samples: the complete 13-system grid contributes
117, and one exploratory Astra/ReAct sample contributes the last. That Astra
sample has a 120-minute budget and one epoch. It can be changed in the manifest
before launch if a different budget is intended.

The shared policy is:

- config `blind`, which renders `sandbox/prompts/blind-v2.txt`;
- budgets 10, 30, and 120 minutes;
- `min_runtime_fraction = 0.75`;
- report target 2,500–3,000 words, with nonempty reports through 3,100 accepted;
- three epochs per base cell and no context cells;
- at most two sample retries after an error;
- one sample and sandbox at a time within each Inspect invocation;
- `--max-connections 2` for Muse and 4 for every other model;
- logs under `logs/round4/<system>/<budget>m`.

Review the fully expanded commands without launching anything:

```sh
uv run python scripts/run_round4.py
uv run python scripts/run_round4.py --lane react
uv run python scripts/run_round4.py --time-limit-minutes 10
uv run python scripts/run_round4.py --system react-gpt-6-astra-exploratory
```

Check credentials, Docker, and the dataset without making model calls:

```sh
uv run python scripts/run_round4.py --check
```

Execution always requires `--execute`. Jobs selected by one invocation run
sequentially and stop at the first failed Inspect command. Run the three lanes
in separate terminals if one Claude, one Codex, and one ReAct cell should be in
flight concurrently:

```sh
uv run python scripts/run_round4.py --lane claude --execute
uv run python scripts/run_round4.py --lane codex --execute
uv run python scripts/run_round4.py --lane react --execute
```

Select a single budget across every lane with `--time-limit-minutes`. Combine
it with `--lane` when launching the same budget in separate terminals:

```sh
uv run python scripts/run_round4.py --lane claude --time-limit-minutes 10 --execute
uv run python scripts/run_round4.py --lane codex --time-limit-minutes 10 --execute
uv run python scripts/run_round4.py --lane react --time-limit-minutes 10 --execute
```

Repeat `--time-limit-minutes` to schedule several budgets together. The
launcher orders cells longest-first and `--parallel-jobs` bounds concurrent
model cells. With three epochs, the following runs at most nine samples per
lane and starts 120-minute cells before 30-minute cells:

```sh
uv run python scripts/run_round4.py --lane claude --time-limit-minutes 120 --time-limit-minutes 30 --parallel-jobs 4 --max-samples 3 --max-sandboxes 3 --resume-existing --execute
uv run python scripts/run_round4.py --lane codex --time-limit-minutes 120 --time-limit-minutes 30 --parallel-jobs 4 --max-samples 3 --max-sandboxes 3 --resume-existing --execute
uv run python scripts/run_round4.py --lane react --time-limit-minutes 120 --time-limit-minutes 30 --parallel-jobs 6 --max-samples 3 --max-sandboxes 3 --resume-existing --execute
```

For narrower staged launches, select one system. This is useful for the initial
native-ReAct cache smoke and for controlling OpenRouter spend:

```sh
uv run python scripts/run_round4.py --system react-gpt-5-6-sol --execute
```

After generation, use `inspect view --log-dir logs/round4` to inspect the
trajectories. Export or replay the successful reports for rubric grading only
after the generation audit is complete.
