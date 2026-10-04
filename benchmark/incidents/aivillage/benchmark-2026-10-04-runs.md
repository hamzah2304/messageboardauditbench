# AI Village benchmark runs, 4 October 2026 (prompt v3.17, 30 minutes)

The run folders to grade, and the folders from the same batch to ignore. Configs `aivillage-v12-30` (no subagents) and `aivillage-v12-30-subagents`; full logs with reasoning traces; 20 ranked findings; 8,000 to 10,000 words. Replicate 1 ran on the VM (heavily CPU-loaded: tool calls about 2 to 3 times slower than unloaded), replicate 2 on Oscar's Mac, so every model has one replicate on each machine; the Sonnet 5.5 subagents replicate 1 ran on the Mac. Muse Spark 1.3's replicate 1 is the folder labelled `r4` (a rerun). Opus 4.6 was dropped; Opus 4.8's two subagent runs were added later the same evening (started 22:21 UTC; the machine was not recorded); the OpenRouter models have no subagent tool.

## Grade these (34 runs)

- `20261004T201424Z_react_meta_muse-spark-1.3_r4_aivillage-v12-30_ba14633557cb`
- `20261004T202856Z_claude_claude-opus-5_r1_aivillage-v12-30_9ac74397f12e`
- `20261004T202856Z_react_google_gemini-3.8-flash_r1_aivillage-v12-30_2760de4fc0e8`
- `20261004T202857Z_codex_gpt-6-astra_r1_aivillage-v12-30_e46ecc18cae0`
- `20261004T202926Z_codex_gpt-6-astra_r1_aivillage-v12-30-subagents_4d0ba09b5ea4`
- `20261004T203210Z_claude_claude-opus-5_r1_aivillage-v12-30-subagents_9d68274e842e`
- `20261004T203210Z_react_moonshotai_kimi-k3_r1_aivillage-v12-30_920e827f33fd`
- `20261004T203245Z_codex_gpt-6.1-sol_r1_aivillage-v12-30_89adb7d41447`
- `20261004T203305Z_claude_claude-opus-4-8_r1_aivillage-v12-30_3c8aaca88f12`
- `20261004T203500Z_claude_claude-opus-5_r2_aivillage-v12-30_7fd943c366d6`
- `20261004T203530Z_claude_claude-opus-5_r2_aivillage-v12-30-subagents_025613e683dc`
- `20261004T203539Z_codex_gpt-6-astra_r2_aivillage-v12-30_b5b6fabf3bb5`
- `20261004T203620Z_react_google_gemini-3.8-flash_r2_aivillage-v12-30_a81a4a60ad73`
- `20261004T203650Z_react_meta_muse-spark-1.3_r2_aivillage-v12-30_79aaef444a7e`
- `20261004T203840Z_claude_claude-opus-4-8_r2_aivillage-v12-30_c92c4a59acd9`
- `20261004T203850Z_codex_gpt-6-astra_r2_aivillage-v12-30-subagents_1646c1ee0f71`
- `20261004T204001Z_react_moonshotai_kimi-k3_r2_aivillage-v12-30_a760d749e01e`
- `20261004T204257Z_react_z-ai_glm-5.3_r1_aivillage-v12-30_cb5d2b96b736`
- `20261004T205826Z_react_deepseek_deepseek-v4-flash_r1_aivillage-v12-30_20a500843a21`
- `20261004T205947Z_codex_gpt-6.1-sol_r1_aivillage-v12-30-subagents_f45a0f26b4f3`
- `20261004T210020Z_codex_gpt-6-luna_r1_aivillage-v12-30_72cb6a3f1af2`
- `20261004T210226Z_claude_claude-sonnet-5-5_r2_aivillage-v12-30_e2c193189981`
- `20261004T210357Z_react_z-ai_glm-5.3_r2_aivillage-v12-30_28d327f83986`
- `20261004T210441Z_codex_gpt-6-luna_r1_aivillage-v12-30-subagents_a6be61aa632f`
- `20261004T210537Z_claude_claude-sonnet-5-5_r2_aivillage-v12-30-subagents_95f647303ee4`
- `20261004T210627Z_codex_gpt-6.1-sol_r2_aivillage-v12-30_17c50389baa8`
- `20261004T210708Z_react_deepseek_deepseek-v4-flash_r2_aivillage-v12-30_4561c650aa1c`
- `20261004T210937Z_codex_gpt-6.1-sol_r2_aivillage-v12-30-subagents_ef29ebb018e6`
- `20261004T213021Z_claude_claude-sonnet-5-5_r1_aivillage-v12-30_9bc1756815c8`
- `20261004T213635Z_codex_gpt-6-luna_r2_aivillage-v12-30_21ba02356d76`
- `20261004T213945Z_codex_gpt-6-luna_r2_aivillage-v12-30-subagents_d8f5f3aea0bb`
- `20261004T214058Z_claude_claude-sonnet-5-5_r1_aivillage-v12-30-subagents_36f507e1d557`
- `20261004T222126Z_claude_claude-opus-4-8_r1_aivillage-v12-30-subagents_ed0051c92b03`
- `20261004T222156Z_claude_claude-opus-4-8_r2_aivillage-v12-30-subagents_e9eff1ea3bc2`

## Ignore these

| Folder | Why |
|---|---|
| `20261004T200232Z_react_z-ai_glm-5.3_r9_aivillage-v12-30_0662a9cca4c2` | 5-minute smoke test on the one-week slice |
| `20261004T201146Z_claude_claude-opus-5_r1_aivillage-v12-30_d7a24c9ddf0f` | killed about 14 minutes in when the first queue processes were stopped; relaunched as the same replicate |
| `20261004T201150Z_claude_claude-opus-5_r1_aivillage-v12-30-subagents_a313809ed708` | killed about 14 minutes in when the first queue processes were stopped; relaunched as the same replicate |
| `20261004T201207Z_claude_claude-opus-4-8_r1_aivillage-v12-30_40e2296709e7` | killed about 14 minutes in when the first queue processes were stopped; relaunched as the same replicate |
| `20261004T201233Z_codex_gpt-6-astra_r1_aivillage-v12-30-subagents_7fe7f1f62111` | killed about 14 minutes in when the first queue processes were stopped; relaunched as the same replicate |
| `20261004T201235Z_codex_gpt-6-astra_r1_aivillage-v12-30_5b4a52b12c44` | killed about 14 minutes in when the first queue processes were stopped; relaunched as the same replicate |
| `20261004T201305Z_react_meta_muse-spark-1.3_r1_aivillage-v12-30_b01ae703504e` | network check failed before the agent started (proxy race, fixed in e107352); replaced by replicate 4 |
| `20261004T201312Z_react_google_gemini-3.8-flash_r1_aivillage-v12-30_e324f880bfa6` | killed about 14 minutes in when the first queue processes were stopped; relaunched as the same replicate |
| `20261004T201323Z_react_moonshotai_kimi-k3_r1_aivillage-v12-30_97e13a60d405` | killed about 14 minutes in when the first queue processes were stopped; relaunched as the same replicate |
| `20261004T210616Z_claude_claude-fable-5-1_r2_aivillage-v12-30_404c3f479f8e` | Fable 5.1 trial run on the Mac; fell back to another model; not in the benchmark |
| `20261004T212950Z_claude_claude-opus-4-8_r1_aivillage-v12-30-subagents_8abaa91b72d0` | Opus 4.8 with subagents, stopped on purpose when Opus 4.8 subagents was dropped |
