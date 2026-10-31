# Practice30 baseline: transcript analysis

Run: official sample agent, Gemma 4 31B, 4.5 min / 100 tool calls per task, 30 trusted tasks.
Result: **11 / 30 solved**. 15 of 19 failures hit the time limit; 7 never edited anything.
Measured with `analysis/analyze_traces.py`; individual runs read with `analysis/show_trace.py`.

## Solved vs. unsolved (averages)

| Signal | Solved | Unsolved |
|---|---|---|
| Seconds per step | 8.6 | 15.9 |
| Thinking per step (chars) | 467 | 1,074 |
| Output tokens per step | 219 | 403 |
| Files read | 5.4 | 10.6 |
| First edit at (s) | 61 | 120 |
| Test runs | 0.7 | 0.1 |
| Graph tool calls | 0.0 | 0.1 |
| Helper (analyzer) agent calls | 0 | 0 |

## The 19 failures, by cause

| Cause | Tasks | What happened |
|---|---|---|
| Out of time while implementing a big change | fastapi_11194, fastapi_13920, fastapi_14306, fastapi_14986, fastapi_9753, fastapi_15589 | Knew the plan, but 24-80 line multi-file fixes do not fit in 4.5 min at ~16 s per step. |
| Overthinking | rich_3180, rich_3278, rich_3953 | Single thinking bursts of 4,000+ tokens (60-130 s) simulating code in its head instead of running it. rich_3953 overflowed the 32K context. |
| Vague issue, wandering | rich_3472, rich_3506, rich_4076, rich_3942, rich_3777, fastapi_15280 | Issue is a few words plus a link the agent cannot open. It re-reads the same files and never commits to a fix. |
| Trusted the old tests | rich_3043 | Found the right file in 10 s, but existing tests expect the old (buggy) output, so it refused to change it. |
| Finished, wrong fix | fastapi_14479, rich_3675, rich_3772 | Plausible fixes that differ from what hidden tests check (exact message wording, exact behaviour). |

## What to change, in order

1. **Cut thinking** (`thinking_budget` 4096 -> small, or off). Overthinking makes every step slower and causes the worst stalls. One config line; test alone first.
2. **Act early**: edit within the first few steps, verify by running a short Python snippet instead of reasoning in the head.
3. **Old tests may encode the bug**: tell the agent hidden tests will expect the fixed behaviour.
4. **Bounded exploration for vague issues**: after a fixed number of reads, commit to the best hypothesis and edit. Any reasonable patch beats an empty one.
5. **Graph tools and the helper agent are never used.** Either teach the agent when to use them or remove them to simplify. Relevant to the paper track.
