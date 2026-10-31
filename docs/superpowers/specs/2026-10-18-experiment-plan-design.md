# Experiment plan: improving the Gemma 4 agent, one measured change at a time

Date: 2026-10-18. Status: **approved** by the owner on 2026-10-18 (E0 approved and run the same day).

## 1. Intent and why

The owner's measure of success by December is **the skills learned**, ahead of leaderboard rank or the paper.
So this plan optimises for learning a transferable method, the one serious agent teams use:
measure fairly, find out why the agent fails, change one thing, prove it helped.
A better score and paper material should come out of that process, not replace it.

## 2. Goals, non-goals, anti-goals

**Goals**
- Learn how noisy our measurements are, and judge every change against that noise.
- Raise the practice solve rate from the 11/30 baseline through single, explained changes.
- After each experiment, write a short plain-language "what we learned" into the guide.
- Use leaderboard submissions (1/day, no GPU quota) as an independent check on milestones.

**Non-goals (for now)**
- LoRA or any training (phase 2, later, learned from scratch).
- Switching to the 12B model (some 12B scorer submissions currently crash; revisit later).
- Temperature tuning (forum measurements show it is mostly noise).

**Anti-goals (would be a failure even if the score rose)**
- Copying a popular public setup wholesale, so we cannot say which part helped.
- Tricks tuned to FastAPI or Rich: the hidden tasks come from other projects.
- Training on Claude or GPT outputs (not allowed by their terms; staff confirmed the rule applies).
- Trusting a single run's +1 or +2 tasks as a real improvement.

## 3. Where we are

Baseline: official sample agent, Gemma 4 31B, `thinking_budget` 4096 with `include_thoughts: true`,
`max_output_tokens` 16384 (harness default), temperature 0.2, 4.5 min and 100 tool calls per task.
Practice set: `experiments/practice30.json` (30 tasks, all verified fair by the controls run).

- **11/30 solved.** 15 of 19 failures timed out; 7 never edited; 1 crashed on the 32K context.
- Failed tasks: 15.9 s per step vs 8.6 s solved; about 2x the thinking per step; first edit at 120 s vs 61 s.
- Failure groups: big multi-file fixes (6), vague reports and wandering (6), overthinking (3),
  wrong fix (3), trusting old tests (1). Graph tools and the helper agent were never used.
- Details: `experiments/practice30-baseline/findings.md`.
- First leaderboard submission (same config) is pending.

## 4. Evidence behind the plan

| Finding | Source |
|---|---|
| Thinking off: 23/129 solved vs 48-51 on. Budget 2048 = 4096 on accuracy (50 vs 48) | Forum 746250 (community, single runs) |
| Thinking budget maps to vLLM `thinking_token_budget`; `thinking_budget: 0` is the only real off switch; `include_thoughts: true` keeps old thoughts in later prompts | Harness `adk_submission/resolvers/generation.py:359-458`; staff in forum 747914 |
| Prompt + `max_output_tokens` above 32,768 is rejected; with 16384 the task crashes once the prompt passes ~16K; 8192 is the common fix | Harness default `swegemma/config.py:59-67`; forum 744692 |
| A timed-out task's working-tree diff is still graded | `swegemma/harness/agent_runner.py:1048-1085` |
| Hiding thoughts (`include_thoughts: false`) cost accuracy (35/129) | Forum 746250 |
| Helper agent adds little; graph tools unused or bloated (~5,800 chars per answer) | Forum 746250, 748323; our transcripts |
| `edit_file` fails when old_string contains `"""` or backticks; the model then repeats the same call | Forum 748323, 747923 |
| Practice scores predict the leaderboard poorly | Forum 744319 |
| Single SWE-bench runs vary 2.2-6.0 points; use several runs, report spread | ICLR 2026 "On Randomness in Agentic Evals" (arXiv 2602.07150) |
| Do error analysis on real failures first, then fix the most common upstream failure | Hamel Husain / Shreya Shankar evals FAQ; Andrew Ng; Anthropic "Demystifying evals for AI agents" |

## 5. Constraints

- Rules: declarative YAML only; one of the four allowed Gemma 4 models; the scorer fixes the vLLM server
  settings and context compaction (we cannot change them); 12 h for all hidden tasks; 1 submission per day.
- GPU quota: 30 h/week, resets every Saturday (next: 2026-10-24). L4x4 counts double.
  One practice30 run is about 2.2 h, which costs about 4.3 h of quota. About 25 h remain this week,
  so **about 5 practice runs** before Oct 24, then about 6 per week.
- Practice environment: subprocess sandbox in Kaggle notebooks (differs slightly from Docker scoring).

## 6. Method (standard practice, applied to our budget)

1. **Fixed suite.** Every experiment runs exactly `practice30.json`, built from `submission/` via
   `notebooks/build_notebooks.py`, so what we test is what we submit.
2. **One variable per experiment.** A "prompt version" counts as one variable.
3. **Paired comparison.** Compare per task against the reference run: tasks newly solved, tasks newly lost.
4. **Noise yardstick (E0).** Re-run the unchanged baseline once. The number of tasks that flip between
   the two identical runs is our noise band.
5. **Outcome plus transcript metrics.** Besides solved/unsolved, record from `analysis/analyze_traces.py`:
   timeouts, seconds per step, output tokens per step, first-edit time, never-edited count,
   context crashes, repeated calls, tool errors, test runs. These move more reliably than the pass count.
6. **Decision rule** *(my call, settled after review)*.
   - **Reference** = the current adopted config, pooled over its two runs (the original baseline and E0 at first).
     Each task gets a reference score of 0, 0.5 or 1.
   - **Gain** = a task the new variant solves that the reference never solved; **loss** = a task the new
     variant fails that the reference always solved. Tasks the reference solved only once are "flaky" and ignored.
   - **Adopt** if (a) gains minus losses is at least 3, or (b) the targeted metric improves clearly
     (timeouts or seconds per step down by at least 20%) with gains minus losses at least 0.
   - **Otherwise not adopted**, and the next experiment builds on the last adopted config. An inconclusive
     result is not retested by default; the one spare run per week goes to the most promising inconclusive result.
   - An adopted variant's single run becomes part of the new reference; if quota allows, a second run is added later.
7. **Same hardware every run** *(my call)*. The scorer uses the same 4x L4 machines as our practice notebooks
   (official "Upgraded Accelerators" page). Every run's log must show 4 L4 GPUs; any run on different hardware is
   discarded and repeated, because its timing metrics are not comparable.
8. **Leaderboard as second opinion** *(my call)*. Practice results decide adoption; experiments do not wait for
   leaderboard results. Submit after each adopted change. The leaderboard is noisy too (about +/-2 of 58 tasks),
   so only a drop of more than 0.05 from the previous submission triggers an investigation (re-read transcripts,
   consider rolling back). The leaderboard also serves as our held-out test, since hidden tasks come from other projects.
9. ~~**No held-out practice set** *(my call)*. Building one costs quota and most remaining practice tasks are broken in
   the notebook environment.~~ **Corrected 2026-10-19 (audit):** this was false. 41 trustworthy tasks were unused.
   A held-out set now exists (see section 10, amendment A1). Prompts must still stay generic (no FastAPI or Rich specifics).
10. **Write-up.** After each experiment: one short "what we learned" in the guide, results in `experiments/<name>/`.

## 7. Experiment queue

| Id | Change (only this) | Hypothesis | Main metric |
|---|---|---|---|
| E0 | None: repeat the baseline | Measures the noise band | Tasks that flip |
| E1 | `thinking_budget` 4096 -> 2048 | Faster steps, fewer timeouts, no accuracy loss | Timeouts, sec/step |
| E2 | `max_output_tokens` 16384 -> 8192 | No context crashes; caps runaway steps | Context crashes, sec/step |
| E3 | Prompt v2: early edit, short thinking, test your fix, edit safety, old tests may encode the bug, bounded exploration for vague issues | Fewer never-edited and wandering tasks | Never-edited, solved |
| E4 | Remove the unused helper agent only (the main agent keeps its graph tools) | Simpler and faster with no loss | Solved, sec/step |
| E5 | Structure: find-the-code step then fix step (SequentialAgent); same tools as before | Better localisation, fewer wandering tasks | Solved, first-edit time |
| E6 | Graph tools: teach when to use them (rewritten instructions) vs. remove them | Do graph tools help a small model locate code? (paper question) | Solved, files read |

**Order change (owner, 2026-10-18, after E0):** E2 runs before E1. E0 showed 4 context crashes; they are deterministic,
destroy finished work, and would muddy the E1 measurement. Run order: E0 → E2 → E1 → E3 → E4 → E5 → E6.

Each later experiment builds on the adopted winners of the earlier ones.
This week's quota covers E0-E3 plus one spare run; E4-E6 fall in the week of Oct 24.

*(My call, after review.)* Graph tools stay available through E4 and E5 so that E6 can test them cleanly;
they matter for the paper. The sample's placeholder LoRA adapters (rank 4, layer 0 only) stay unchanged in every
experiment so they are not a hidden variable. Removing them is a candidate later speed experiment,
since serving any LoRA costs about 11% decode speed (forum 749191).

## 7b. Amendments after the methodology audit (2026-10-19)

An independent reviewer audited every stage against published standards (SWE-bench task validation, Miller 2024
"Adding Error Bars to Evals", the NeurIPS checklist, Anthropic's agent-eval guidance, SWE-agent's dev/test split,
Blum & Hardt on reusing a holdout). Verdict: the direction (eval-driven, error analysis first, one change at a time,
pre-registered rule) is standard; the statistics and the dev/test separation were not. Amendments:

- **A1 · Held-out test set.** `experiments/heldout30.json`, 30 of the 41 unused trustworthy tasks, drawn by
  `experiments/make_heldout.py` (seed 20261019, stratified 12 fastapi / 18 rich; sha256 of committed file 9f1f4e4a986d5063…; task list is what matters). Never used for
  error analysis or prompt writing. Each adopted milestone version runs on it once. `practice30` is now the dev set.
- **A2 · Statistics.** `analysis/compare.py` (tested in `analysis/test_compare.py`): exact McNemar test and seeded
  task-level bootstrap 95% CI for every comparison, plus a per-task solve-rate matrix. Applied retroactively:
  every comparison so far has p = 1.00 and a CI spanning zero (largest: E3 vs pooled reference +6.7 pp,
  CI [-3.3, +17.8]). Power: with one 30-task run, only effects of about +10 pp or more are detectable, and then only
  about a third of the time. "Not kept" therefore means "not detectably better", not "no effect".
- **A3 · Rule (b) calibrated.** A targeted metric only counts if its change exceeds the spread seen between the two
  identical baseline runs (timeouts 15 vs 11, so a change of at least 5 timeouts), or if the mechanism is
  deterministic and verified (E2: prompt + 16,384 output > 32,768 tokens). E2 stays kept on the second ground.
  The metrics actually used (context crashes for E2, never-edited for E3) are hereby recorded as the targets.
- **A4 · Replicate before claiming.** Spare runs go to replicates of promising results, not to new variants.
  E3.1 (already running when this was agreed) is labelled exploratory.
- **A5 · Analysis fixes.** `seconds` in trace stats is agent-only time (results.csv also includes setup and
  grading); `sec_per_step` now includes the first step; `first_edit_or_end_s` counts never-edited tasks at their end
  time so averages cover all tasks. Every run now saves `run_info.json` (build commit, uncommitted-changes flag, GPUs).
- **A6 · Task validation repeated.** Two more CPU-only control runs (`gemma4-task-controls-r2`, `-r3`) to drop any
  task whose verdict flips (flaky tests), as SWE-bench does.
- **A7 · Leaderboard.** One public score has a 95% CI of about ±0.09 (0.12 → [0.06, 0.23]). It is a sanity check
  with tolerance ±2 SE, not a selection tool; the private leaderboard is the only confirmatory number.
- **A8 · Labels for the paper.** Exploratory: failure taxonomy, solved-vs-unsolved correlations, E1, E3, E3.1,
  reproduce-first behaviour, pooled-reference choices, practice-vs-leaderboard ratio, graph-tool misuse.
  Confirmatory: E2's crash elimination; the final version vs the baseline on the held-out set; E6 if its hypothesis
  is committed before it runs.
- **Open:** publishing transcripts (needed for Verifiability) waits on a check of the competition's data rules;
  the wheelhouse dataset version is not yet pinned.

## 8. Results log

### E0 · repeat of the unchanged baseline (2026-10-18, kernel `gemma4-e0`)

| | Run 1 (`gemma4-practice30`) | E0 (`gemma4-e0`) |
|---|---|---|
| Solved | 11 / 30 | 12 / 30 |
| Timeouts | 15 | 11 |
| Context crashes (32K) | 1 | **4** |
| Avg seconds per task | 237 | 233 |
| Sec/step, solved vs unsolved | 8.6 vs 15.9 | 9.2 vs 17.9 |
| Never edited | 7 | 7 |

- **Noise band: 3 of 30 tasks flipped** (gained `fastapi_11194`, `rich_3043`; lost `rich_4077`), about 10%.
  Net +1 with no change at all, which confirms that a +1 or +2 result means nothing on its own.
- **Reference for E1 onward** (pooled over both runs):
  - always solved (10): fastapi_13537, fastapi_14458, fastapi_14786, fastapi_14794, fastapi_9555, rich_2725, rich_2943, rich_3454, rich_3518, rich_3905
  - flaky, ignored (3): rich_4077, fastapi_11194, rich_3043
  - never solved (17): all others. A gain must come from these; a loss from the always-solved 10.
- **The failure pattern replicated**: unsolved tasks again took about 2x longer per step with about 2x the thinking,
  and the same 7-task "never edited" count. The error analysis is stable, not a one-run artefact.
- **Context crashes rose from 1 to 4.** Each crash threw away a finished task. This strengthens the case for E2.
  Open question for the owner: run E2 (output limit) before E1 (thinking budget), since crashes are deterministic
  and also interfere with measuring E1.
- Files: `experiments/e0/` (results, per-task trace stats, patches).

### E2 · output limit 16,384 → 8,192 (launched 2026-10-18, kernel `gemma4-e2`)

- The only change: `max_output_tokens` in `submission/configs/sampling.yaml` (shared by the main and helper agent).
  Verified by diffing the embedded agent files of the E0 and E2 notebooks: 1 line in 1 of 8 files.
- Target metric: context crashes (reference: 1 and 4). Also watched: timeouts, seconds per step, solved.
- **Result (2026-10-18): KEPT** by rule (b): the targeted metric improved by 100% with net 0 solved.

| | Run 1 | E0 | **E2** |
|---|---|---|---|
| Solved | 11 | 12 | **13** |
| Context crashes (task-ending) | 1 | 4 | **0** |
| Timeouts | 15 | 11 | 15 |
| Empty patch (never edited) | 7 | 7 | 6 |
| Avg / max seconds per task | 237 / 499 | 233 / 276 | 245 / **572** |

- Gains: `rich_3278`. Losses: `rich_2725` (timed out). Net 0. All 3 flaky tasks solved this time (not counted).
- **One helper-agent overflow remains**: on `rich_3472` the analyzer sub-agent was used (first time in any run) and its
  24,577-token prompt + 8,192 output passed 32,768. It failed only that tool call; the task continued and timed out.
- ~~New risk: overrunning the time cap.~~ **Corrected 2026-10-19: false alarm.** The 572 s for `rich_3772` is total time
  including ~300 s of grading (its tests are slow); the agent itself never exceeded ~271 s in any run. Grading time is
  excluded from the 12-hour limit, so no mitigation is needed.
- Graph tools were misused once: the agent searched for the issue number ("3417") instead of a symbol (evidence for E6).
- **New reference for E1** *(my call)*: pool all three runs (Run 1, E0, E2). A crash fix should not change how
  non-crashing tasks behave, and three runs give a firmer split:
  - always solved, 3/3 (9): fastapi_13537, fastapi_14458, fastapi_14786, fastapi_14794, fastapi_9555, rich_2943, rich_3454, rich_3518, rich_3905
  - flaky, 1-2/3 (5): fastapi_11194, rich_2725, rich_3043, rich_3278, rich_4077 (ignored)
  - never solved, 0/3 (16): all others
- Leaderboard: not submitted yet; the first submission is still pending, and Kaggle allows only one pending at a time.
- Files: `experiments/e2/`.

### E1 · thinking budget 4096 → 2048 (launched 2026-10-18 ~20:50, kernel `gemma4-e1`)

- The only change vs. E2: `thinking_budget` in `submission/configs/sampling.yaml` (E2's 8,192 output limit stays).
  Verified by diffing the embedded agent files of the E2 and E1 notebooks: 1 line in 1 of 8 files.
- Target metric: timeouts and seconds per step (reference: 15/11/15 timeouts; ~14-18 s per step on unsolved tasks).
- Judged against the pooled 3-run reference: 9 always, 5 flaky, 16 never.
- **Result (2026-10-18 23:35): NOT KEPT.** Config reverted to `thinking_budget: 4096`; E2 remains the current version.

| | Run 1 | E0 | E2 | **E1** |
|---|---|---|---|---|
| Solved | 11 | 12 | 13 | **12** |
| Timeouts | 15 | 11 | 15 | **15** |
| Context crashes | 1 | 4 | 0 | **0** |
| Mean seconds per step | 9.9 | 10.0 | 10.1 | **9.3** |
| Longest single step (output tokens) | 4,538 | 4,256 | 4,139 | **2,262** |
| Steps over 2,048 tokens | 9 | 11 | 12 | 13 (capped) |

- Gains: `fastapi_9753`, `rich_3777`. Loss: `rich_3454`. Net +1, inside the noise (rule a fails).
- Timeouts unchanged and seconds per step only -7%, below the 20% bar (rule b fails).
- **Why it barely mattered (the lesson):** the cap worked (longest step 4,500 → 2,262 tokens) but only ~2% of steps
  ever exceed 2,048 tokens; 95% are under ~1,000. Time is lost to **many ordinary steps** (~25 steps × ~10 s fills the
  4.5 minutes), not to rare thinking bursts. Our earlier "overthinking" diagnosis was right about the worst cases
  but wrong about where most of the time goes.
- **Consequence for the plan:** the main lever is the **number of steps**, which is E3's target (edit early, stop
  wandering). E1 stays a candidate for the weekly spare run only if E3 leaves time-per-step as the bottleneck.
- Files: `experiments/e1/`.

### E3 · prompt v2 (launched 2026-10-19 ~00:00, kernel `gemma4-e3`)

- The only change vs. E2: `submission/prompts/system.md` replaced by prompt v2 (`experiments/e3/system_v2_draft.md`,
  commit `0a95530`, sha256 6d32dab2…), approved by the owner after two review rounds:
  research on standard practice, then a check against the harness's own injected instructions
  (fixed: final text reply after `submit_patch`; glance at tests while locating; removed FastAPI-specific and
  duplicate rules). `sampling.yaml` settings identical to E2 (only a comment differs).
- Rules and the failure each targets: step budget with first edit by step 8 (never-edited), one tool call per
  step and short thinking (slow steps), run code instead of tracing (overthinking), no re-reading (wandering),
  symbol names for graph tools ("3417" misuse), vague-issue rule (wandering), old tests may encode the bug
  (`rich_3043`), exact wording (`fastapi_14479`), edit-safety rules (failed/repeated edits).
- Judged against E2 as the current version, with the pooled reference (9 always, 5 flaky, 16 never).
  Main metrics: never-edited (E2: 6), timeouts (E2: 15), solved. Rule compliance also checked in traces:
  first-edit time, re-reads, repeated identical calls, tool errors.
- Standard-practice basis: bundled prompt version judged on the same task set, then leave-one-out ablation
  only if it wins (SWE-agent, OpenAI GPT-4.1 guide); see research notes in the conversation record.
- **Result (2026-10-19): INCONCLUSIVE, not adopted by the rule.** Best score so far, but the targeted behaviour moved
  the wrong way.

| | E2 (current) | **E3** |
|---|---|---|
| Solved | 13 | **14** |
| Losses among the 9 always-solved | 1 | **0** |
| Gains among the 16 never-solved | — | 2 (`fastapi_9753`, `rich_3777`; both were also E1's gains) |
| Timeouts | 15 | 14 |
| Tasks with no source change | 6 | **8** |
| First source edit, solved / unsolved tasks | 65 s / 108 s | **97 s / 153 s** |
| Submitted explicitly | 12 | 15 |
| Mean seconds per task | 245 | 224 |

- Rule (a): net +2 < 3. Rule (b): the targeted metric (never-edited) got worse, 6 → 8. Not adopted.
- **Compliance check (the key finding):** the "first edit by step 8" rule was mostly ignored. Prompt v2 pushed Gemma
  toward *reproduce first*: 3 of the 8 empty tasks only wrote `/tmp/repro.py` and never edited source. This helped the
  solvable tasks (more explicit submits, zero losses) but delayed edits on hard ones.
- **Measurement bug fixed:** `analysis/analyze_traces.py` counted `/tmp` scratch files as edits. It now reports source
  edits, scratch writes and agent-only seconds separately; all runs' stats were recomputed.
- Leaderboard: the first submission (official sample + 4.5 min budget) scored **0.12** public, while the same config
  solved 11-12/30 (37-40%) on practice. Practice overestimates the leaderboard about 3x, consistent with harder,
  unseen projects in the hidden set (and with forum reports).
- Files: `experiments/e3/` (results, trace stats, patches, the approved prompt).
- Live prompt reverted to the E2 version after this result (commit `76311af`).

### E3.1 · prompt v2.1 (launched 2026-10-19 ~08:30, kernel `gemma4-e3-1`, this week's spare run)

- Owner's choice for the spare run (over repeating E3 unchanged): fix the observed non-compliance.
- Prompt v2.1 = v2 with exactly two lines changed (`experiments/e3_1/system_v2_1.md`):
  "first edit **to the source code** by step 8; a script in `/tmp` does not count as an edit" and
  "run a one-line `python3 -c` check; no longer reproduction scripts before the first source edit".
- Verified: only `prompts/system.md` differs from E2 (settings identical); embedded prompt equals v2.1.
- Judged against E2 (current version) with the same pooled reference. Main metrics: tasks with no source change
  (E2: 6, E3: 8), first source edit time, solved. Also compared with E3 to see if the fix changed behaviour.
- Leaderboard: owner chose to hold today's submission until E3.1 is in, then submit the best version.
- **Result (2026-10-19): NOT ADOPTED (exploratory).**

| | E2 (current) | E3 | **E3.1** |
|---|---|---|---|
| Solved | 13 | 14 | **15** |
| Gains / losses vs E2 | — | — | 2 / 0 (`rich_2725`, `rich_3506`), McNemar p = 0.50, CI [+0.0, +16.7] pp |
| Gains / losses vs pooled reference (run 1, E0, E2) | — | — | 1 / 0, net +1 |
| Timeouts | 15 | 14 | 12 |
| Tasks with no source change | 6 | 8 | **6** |
| Tasks that wrote `/tmp` scratch files | 0 | 21 | **17** |
| First source edit or end, median | 84 s | 141 s | **125 s** |

- Rule (a): net +1 < 3. Rule (b): the targeted metric (no source change) is back to E2's 6, not better; timeouts
  15 → 12 is below the 5-timeout noise threshold (A3). Not adopted.
- **Compliance:** the two-line fix only partly worked. Scratch-script tasks fell 21 → 17 and empty tasks 8 → 6, but
  Gemma still edits later than with the official prompt (median 125 s vs 84 s). A sentence in the prompt is not
  enough to override its "reproduce first" habit; a structural change (E5, a separate find/fix step) is the better lever.
- **Pattern worth checking:** the two v2-family runs solved 14 and 15; the three E2-style runs solved 11, 12, 13.
  Against the pooled reference E3.1's CI is [+2.2, +18.9] pp, the first one not to cross zero, but this run was
  exploratory and the reference mixes configs. Per A4, this earns a **replicate** next week (confirmatory), not adoption.
- Files: `experiments/e3_1/` (results, trace stats, patches, prompt).

### A6 result · task-check repeats (2026-10-19)

- 128 of 129 tasks gave the same verdict in all three control runs. The one flip, `rich_3782` (broken → trustworthy
  → trustworthy), is in neither the dev set nor the held-out set and stays excluded. No changes to `practice30.json`
  or `heldout30.json`.

### Week of Oct 24 · E5/E6 design runs (spec `2026-10-19-e5-e6-structure-vs-prompt-design.md`, plan `2026-10-23-e5-e6-oracle.md`)

Quota on 2026-10-24: 30 h, 0 used; next reset 2026-10-31 00:00 UTC. Gate G4 passed (pooled split 35/29/21).
Baseline for H1a from G4: first write was a source edit in E2 24 of 24 writing tasks, E3.1 10 of 26.

#### Run 1 · ORACLE (launched 2026-10-24, kernel `gemma4-oracle`, confirmatory for H2)

- Arm: E2 unchanged, plus `hints_text` = gold source files and functions (`experiments/oracle/hints.json`). Practice
  only, never submitted.
- H2 (written before launch): ORACLE solves more than the E2-style pooled mean of 12.
- Scheduling rule: solved ≥ 15 → E6 stays this week; solved ≤ 14 → runs 5-6 become E5/ORACLE runs. One run is
  inside the noise band, so the paper's bottleneck claim needs ORACLE r2.
- Also recorded: `gold_files_edited` (did the patch touch the hinted files), first write kind, timeouts.
- **Result (2026-10-24): 14/30 solved.** vs pooled reference: gains 1, losses 1, net 0; +6.7 pp, 95% CI [-4.4, +17.8].
  vs E2: 14 vs 13, McNemar p = 1.00. Timeouts 14. Run clean (commit a8f5039, harness sha ok, 4 GPUs).
- **Scheduling rule applied: 14 ≤ 14 → E6 is deprioritized this week**; runs 5-6 become E5/ORACLE runs.
- H2: not supported by this run (+2 over the pooled mean, inside the noise). ORACLE r2 is needed for the paper claim.
- **Where failures moved** (unsolved tasks, by patch files): E2 no source edit 6 / wrong files 8 / right files 3 →
  ORACLE 3 / 3 / 10. Knowing the location almost removed "never edited" and "wrong file", but most of those tasks
  then failed on the fix itself or ran out of time (24 of 30 patches touched every gold file; only 14 solved).
  Exploratory reading: at a 4.5-minute budget, localization is not the main bottleneck for E2; fixing correctly in
  time is.

#### Offline gates (2026-10-24)

- G1 passed: `tools/check_submission.py` (competition validator + compiler, google-adk 1.36.1, harness wheels) gives
  OK for `submission/`, `experiments/e5/submission`, `experiments/e6/submission`; a copy with a stray `{foo}` fails.
- G2 passed: `tools/sim_pipeline.py` (real ADK, scripted model) shows the localizer's answer reaches the fixer
  through `{localization?}` and the harness task message reaches the fixer, for E5 and E6. Known cost recorded: one
  continuation nudge re-runs the localizer (2 localizer passes). A copy without `output_key` fails the check.
- G4 passed earlier (35/29/21).
- G3 FAILED by the pre-registered rule (graph hit rate must be at least grep's): `search_similar_code` put all gold
  files in its top 5 for 8 of 30 tasks, grep for 11 of 30 (`experiments/graph_probe/graph_probe.csv`, kernel
  `gemma4-graph-probe` v3; v1 and v2 failed on two notebook bugs, fixed with tests). The two methods are
  complementary: graph-only hits 4, grep-only hits 7, either 15 of 30. Caveat: symbols come from issue text, and
  7 rich issues yield no usable code names (only github.com/CHANGELOG), which handicaps both methods equally.
- Consequence (spec section 5): E6 runs as "graph-first" (E5's localizer tools, prompt requires graph calls before
  any grep). RQ3 restated before launch: does a dedicated graph-first stage make the model use graph tools (H3a),
  and does that change localization accuracy vs E5? H3b is dropped; this probe is reported as the RQ3 evidence that
  graph search loses to grep on these repos, consistent with LocAgent's ablation.
- Prompts approved by the owner 2026-10-24.

#### Run 2 · E5 r1 (launched 2026-10-24, kernel `gemma4-e5`, confirmatory for H1a/H1b)

- Arm: `experiments/e5/submission` (SequentialAgent localizer → fixer; owner-approved prompts; E2 settings).
- H1a (written before launch): among tasks with any file write, the share whose first write is a source edit is at
  least 25 percentage points above E3.1's (10 of 26 = 38%), i.e. at least 63%, in both E5 runs.
- H1b: tasks ending with no source edit are no more than E2's 6, in both E5 runs.
- Also recorded: finder file/function hit rate vs gold, finder share of time, nudges and localizer re-runs, solved,
  timeouts; paired comparisons vs the E2 pooled reference and vs E3.1.
- Stop rules: more than 3 harness-level failures → fix and re-run, not counted; median finder time above half of the
  median agent time → run 4 becomes E5b (revised localizer prompt, committed before launch) instead of E5 r2.
- **Result (2026-10-24): 10/30 solved.** vs pooled reference: gains 0, losses 2, net -2; -6.7 pp, CI [-18.9, +3.3].
  vs E2: 10 vs 13, McNemar p = 0.375. vs E3.1: 10 vs 15, p = 0.062, CI [-30.0, -3.3]. Timeouts 18. Run clean
  (commit 2511c4f, harness sha ok, 4 GPUs). No nudges, no localizer re-runs.
- **Stop rule triggered:** the localizer took a median 177 s of a median 231 s of agent time (77%), with a median of
  11 tool calls despite the prompt's "about 8". So run 4 becomes **E5b**, not E5 r2.
- H1a: 13 of 13 tasks that wrote a file wrote source first (100% ≥ 63%), and no task wrote a scratch file (E3.1: 17).
  Met, but only 13 tasks wrote anything at all, so this is weak support.
- H1b: **failed**: 18 tasks ended with no source edit (E2: 6). The fixer often had no time left.
- Localizer accuracy: named every gold file on 16 of 30 tasks; every gold function on 8 of 28.
- Exploratory reading: the structure enforced exactly what it controls (no edits and no scratch files in stage 1,
  zero `/tmp` scripts), and what was left to the prompt (stage 1's length) was again not followed. Same lesson as
  E3/E3.1, now inside the pipeline.

#### Owner decisions after runs 1-2 (2026-10-24)

- E5b = localizer with **no tools**: it answers in one step from the issue and the workspace file list in the task
  message (Agentless's first stage), so stage 1's length is fixed by structure, not by the prompt. Chosen over a
  stricter prompt ("at most 5 calls"), which E3, E3.1 and E5 suggest Gemma would ignore. Deviation from the stop
  rule's wording ("revised localizer prompt"), recorded here: the revision is structural.
- Runs left this week (about 21 h): run 3 E3.1 r2 (now), run 4 E5b r1, run 5 E5b r2, run 6 ORACLE r2.

#### Run 3 · E3.1 r2 (launched 2026-10-24, kernel `gemma4-e3-1-r2`, confirmatory)

- Arm: `submission/` with `prompts/system.md` = `experiments/e3_1/system_v2_1.md` (identical to E3.1 r1).
- Predictions written before launch: (1) the prompt rule backfires again: first write is a `/tmp` script on at least
  10 of the tasks that write a file (r1: 16 of 26); (2) the v2 family beats the E2 style: E3.1 r2 solves at least
  13 (r1: 15; E2-style runs 11, 12, 13). Pooled over r1 and r2, compared with the pooled E2 reference.
- **Result (2026-10-24): 13/30 solved.** Run clean (commit f133a4e, harness sha ok, 4 GPUs). Timeouts 14.
- Prediction 1 **held**: first write was a `/tmp` script on 14 of 24 writing tasks (r1: 16 of 26). The backfire
  replicates: pooled over both runs, 30 of 50 writing tasks (60%) started with a scratch script, vs 0 of 24 for E2.
- Prediction 2 **held, barely**: 13 ≥ 13. vs pooled reference net +1, +3.3 pp, CI [-5.6, +12.2]; vs E3.1 r1 13 vs
  15, p = 0.625. Pooled v2.1 solves 28 of 60 (47%) vs E2-style 36 of 90 (40%): not distinguishable from noise.

#### Run 4 · E5b r1 (launched 2026-10-24, kernel `gemma4-e5b`, confirmatory for H1a/H1b with E5b r2)

- Arm: `experiments/e5b/submission`: E5 with a tool-less localizer (one reply from the issue and the 3-level
  directory tree in the task message). Fixer unchanged. Prompt approved by the owner 2026-10-24.
- Predictions written before launch: (1) structure fixes stage 1's length: median localizer time at most 60 s;
  (2) H1a: at least 63% of writing tasks write source first; (3) H1b: no more than 6 tasks end with no source edit;
  (4) solved at least E5's 10 (exploratory; compared with the E2 pooled reference and with E3.1 r1+r2).
- Also recorded: localizer file/function hit rate (expected lower than E5's 16/30 because it cannot read code).
- **Result (2026-10-24): 12/30 solved.** Run clean (commit 1a691d7, harness sha ok, 4 GPUs). Timeouts 16.
- Prediction 1 **held**: median localizer time 11 s (E5: 177 s); one task took 168 s after a nudge re-ran it.
- Prediction 2 (H1a) **held**: 22 of 22 writing tasks wrote source first; zero scratch scripts.
- Prediction 3 (H1b) **failed**: 8 tasks ended with no source edit (bar: 6; E5: 18).
- Prediction 4 **held**: 12 ≥ 10. vs pooled reference net -2, 0.0 pp, CI [-12.2, +10.0]; vs E2 12 vs 13, p = 1.00;
  vs E5 12 vs 10, p = 0.688; vs E3.1 r1 12 vs 15, p = 0.25.
- Localizer accuracy, as expected lower than E5: all gold files named on 12 of 30 (E5: 16), functions 5 of 28.
- Fixer's first source edit came a median 116 s after it started.
- Exploratory reading: limiting stage 1 by structure worked exactly (11 s), and kept the behavioural effect
  (100% source-first, 0 scratch), but the score only returned to E2's level. Consistent with ORACLE: better or
  earlier location information does not buy solves at this budget; the fix itself is the bottleneck.

#### Runs 5-6 (launched 2026-10-24; quota before launch: 12.8 h left)

- **Run 5 · E5b r2** (`gemma4-e5b-r2`), same notebook config as run 4. Confirmatory predictions, judged on r2 alone
  and pooled with r1: median localizer time at most 60 s; at least 63% of writing tasks write source first; no more
  than 6 tasks with no source edit (failed in r1 with 8); solved within the E2 pooled range (11-13).
- **Run 6 · ORACLE r2** (`gemma4-oracle-r2`), same as run 1. Prediction for the bottleneck claim (C3): with the
  location given, unsolved tasks are dominated by "right files, wrong fix" (at least half of unsolved, r1: 10 of 16)
  and solved stays within 2 of the E2 pooled mean (r1: 14).
- **Run 5 result (2026-10-24): E5b r2 11/30.** Clean (03a4f80, sha ok, 4 GPUs). Timeouts 17.
  - Localizer median 11 s: **held** (r1: 11 s). Source-first 23 of 23, zero scratch: **held** (pooled 45 of 45).
  - No source edit 7: **failed** (bar 6; r1: 8). H1b fails in both runs, so it is not supported.
  - Solved 11, within 11-13: **held**. vs r1: 11 vs 12, p = 1.00; vs pooled reference net 0, CI [-15.6, +7.8].
  - Localizer named all gold files on 12 of 30 (r1: 12).
- **Run 6 result (2026-10-24): ORACLE r2 13/30.** Sha ok, 4 GPUs; build flag dirty only because of the uncommitted
  e5b_r2 notebook folder (see ledger), code at 03a4f80. Timeouts 14.
  - Solved 13, within 2 of 12: **held**. vs r1: 13 vs 14, p = 1.00; vs pooled reference net +2, CI [-7.8, +15.6].
  - "Right files, wrong fix" at least half of unsolved: **failed narrowly** (8 of 17; needed 8.5). Unsolved split:
    no source edit 8 / wrong files 1 / right files 8.
  - Pooled ORACLE r1+r2: 27 of 60 (45%) vs E2-style 36 of 90 (40%). Unsolved pooled: no source edit 11, wrong
    files 4, right files wrong fix 18. With the location given, only 4 of 33 failures are about the wrong place;
    the rest are wrong fixes or not finishing in time. C3 is restated accordingly (location rarely the failure
    once given; given location does not raise solves detectably).

### CORRECTION 2026-10-24 (independent code review of the measurement code)

The whole-branch review found that `first_write_kind`, `edits` and `patch_overlap` treated any path outside `/tmp`
as source code. Real traces show that the reference agent's first write is usually a reproduction script at the
repository root (`reproduce_issue.py`, `repro.py`), and the E3.1 prompt explicitly says to put scratch scripts in
`/tmp`. So the earlier metric measured where scripts were saved, not whether the agent edited source first.
Fixed (tests first): source = a file inside a package folder that is not a test or repro script; repo-root new
files, tests and `/tmp` are scratch; redirect regex no longer matches `->`/`>=` or quoted code; path-less writes are
ignored; the fixer clock starts when the localizer's last step ends; steps without token metrics are ignored for
compaction. All runs were recomputed. Entries above are kept as written; the corrected numbers below supersede them.

| Arm | Runs | Source-first / writing tasks | No source edit | Unsolved: no edit / wrong files / right files |
|---|---|---|---|---|
| Reference (Run 1, E0, E2) | 3 | 6/23, 8/23, 4/24 = **18/70 (26%)** | 12, 9, 11 | E2: 11 / 3 / 3 |
| E3 (prompt v2) | 1 | 9/25 | 10 | 10 / 2 / 4 |
| E3.1 (prompt v2.1) | 2 | 10/26, 9/24 = **19/50 (38%)** | 6, 10 | r1: 7 / 4 / 4 |
| E5 | 1 | 10/13 | 18 | 18 / 0.5 / 1.5 |
| E5b | 2 | 13/21, 11/23 = **24/44 (55%)** | 12, 12 | 14 / 2 / 2; 13 / 1.5 / 4.5 |
| ORACLE | 2 | 12/27, 10/23 | 6, 8 | 6 / 0 / 10; 9 / 0 / 8 |

- Fisher exact, source-first share: E3.1 vs reference 38% vs 26%, p = 0.17 (not significant); pipeline arms E5+E5b
  vs reference 34/57 (60%) vs 26%, p = 0.0001; E5b alone p = 0.003.
- G4's pooled split (Run 1, E0, E2, E3, E3.1) is 50 / 14 / 21, not 35 / 29 / 21: most failures never edit source.
- Verdict changes:
  - "The E3.1 rule backfired (30 of 50 scratch-first)" is **withdrawn**. The rule moved scratch scripts to `/tmp`
    as instructed and did not significantly change editing order.
  - H1a as pre-registered used the `/tmp` definition written in the spec, and the code matched it; under the
    corrected definition E5 meets the 63% bar (10/13, 77%) and E5b does not (62%, 48%). Reported both ways.
  - H1b's bar "E2: 6" becomes 11 under the corrected definition; E5b (12, 12) is not better than the reference.
  - E5b's "zero scratch scripts" is withdrawn: its fixer still wrote a repro script first on 20 of 44 tasks.
  - ORACLE: wrong-file failures drop to 0 in both runs (reference E2: 3); "never edited" goes from 11 (E2) to 6
    and 9. Solve rate unchanged within noise.
- ORACLE hint caveat: function names come from diff hunk headers, which name the nearest def before a hunk; on
  about 4 tasks the hinted function was wrong (e.g. a nested helper named instead of the enclosing function that changed).
  Files were always right. Future ORACLE hints name files only.
- The localizer timing results (E5 177 s with a prompt limit ignored; E5b 11 s by structure) are unaffected.

### Week of Oct 31 · held-out confirmation (APPROVED by owner 2026-10-24; locked, predictions as below)

- Amendment A9 (approved 2026-10-24): the held-out check uses **41 tasks** = `heldout30.json` (seed 20261019) plus the 11
  trusted tasks never used (FastAPI 4, Rich 7). None of the 41 has been looked at while designing arms. More tasks
  give more power on the one comparison that counts as confirmatory.
- Runs (about 6 h of quota each at 41 tasks; 30 h available): E2, E3.1, E5b, ORACLE on the 41 tasks, back to back in
  that order, plus one spare for a failed run. No other GPU runs that week.
- Predictions (confirmatory; tests named in advance):
  - (Revised after the 2026-10-24 correction; approved 2026-10-24.) C1 (literal compliance): among
    scratch-first tasks, E3.1 puts the script under /tmp in at least 80%, E2 in at most 20% (Fisher p < 0.05).
    The source-first difference E3.1 minus E2 is reported as an estimate with a 95% CI; we make no "no effect"
    claim, because a non-significant test cannot show absence of an effect. C2: E5b's source-first share exceeds E2's (Fisher p < 0.05);
    localizer median at most 60 s.
  - C3: ORACLE solves at most 4 more tasks than E2 (about 10 pp) and, among ORACLE's unsolved tasks, at most 15%
    touched only wrong files. ORACLE hints name files only (no function names).
  - Solve rates for all arms are reported with exact McNemar vs E2 and bootstrap CIs; no solve-rate claim is
    pre-registered (power is too low to promise one).
- Builder work before Oct 31 (no GPU): task-list parameter for arms (`heldout41`), ORACLE hints for the 41 tasks,
  `analysis/paper_tables.py` so every number in the paper is generated from the CSVs, Fisher test in `compare.py`.
- Builder work done 2026-10-31 (tests first): `experiments/heldout41.json` (made by `experiments/make_heldout41.py`;
  FastAPI 16, Rich 25; committed-file sha256 prefix 85640eb6ba3d6e8f (of the committed LF file); all 41 trusted), arms `e2_h41`, `e3_1_h41`,
  `e5b_h41`, `oracle_h41`, files-only hints (`python analysis/gold.py hints heldout41`, git-ignored),
  `compare.fisher_exact`, trace column `first_write_in_tmp`. `paper_tables.py` still to do.

#### Amendment A10 (2026-10-31, after an independent methodology review, BEFORE any held-out data was seen)

Supersedes the C1-C3 wording above where they differ. Analysis code frozen at commit `352a0dd`
(`analysis/heldout_tests.py`, run as `python analysis/heldout_tests.py e2_h41 e3_1_h41 e5b_h41 oracle_h41`).
A dry run on the dev set (practice tasks, not held-out) passes all three tests on both dev replicates.

- **Fixed-sequence testing** C1 then C2 then C3, each at alpha 0.05, stopping at the first failure; later claims
  are reported as not tested.
- **C1, manipulation check** (literal compliance): among scratch-first tasks, E3.1 puts the script under /tmp in at
  least 80% AND E2 in at most 20% AND one-sided Fisher p < 0.05.
- **C2, primary**: per task over all valid tasks, "first file write is a source edit" (a task with no write = 0);
  E5b vs E2, one-sided exact McNemar on discordant tasks, p < 0.05. Sensitivity (must point the same way):
  writers-only one-sided Fisher. Manipulation check: E5b localizer median at most 60 s. Expected power is about
  0.6 at the dev effect size; a null is reported as "not detected", with the estimate and CI, never as "no effect".
- **C3**: the one-sided 95% upper bound (paired bootstrap, 10,000 resamples, seed 20261019) of the ORACLE minus E2
  solve-rate difference is below +15 pp. Scope: file-level location, at this budget. Manipulation check: share of
  ORACLE's unsolved tasks with patch_overlap == none (touched only wrong files).
- **Estimates, no test**: source-first differences E5b minus E3.1 (the ask-vs-enforce comparison in the title),
  E5b minus ORACLE (structure beyond location information) and E3.1 minus E2, each with a 95% bootstrap CI.
- **Harness failures**: a task where any arm's gold patch fails, or that ends in an error other than the session
  timeout, is dropped from every paired comparison.
- **Runs in parallel**: the four arms launch together (amends "back to back in that order"), so all arms run under
  the same conditions. Launch time, GPUs and sec/step are recorded per run.
- **Spare run**: if no run fails, it becomes E5b r2 on the same 41 tasks, a replication; primary tests use r1 only
  and r2 is reported as agreement in direction.
- **Per-repo** source-first counts are reported (FastAPI 16, Rich 25 tasks).
- **Disclosed confounds**: E5b's fixer receives location notes and is told to start by editing those locations, so
  C2 mixes no-edit structure, handed-over location and a prompt instruction (the E5b minus ORACLE estimate
  addresses this); E5b drops the rarely used helper; held-out ORACLE is files-only, unlike dev ORACLE; the fixer
  preamble says the localizer read the code, which is not true for E5b (wording kept so the arm is unchanged); the
  dev reference pool includes Run 1 (16,384 output limit); vLLM sampling is not deterministic (tasks are the unit).

#### Held-out launches (2026-10-31)

- All four notebooks built in one process from commit 61c7f8b (uncommitted changes: none; 41 tasks each).
- 10:41 IST: `gemma4-e2-h41` and `gemma4-e3-1-h41` launched. Kaggle refused the other two ("Maximum batch GPU
  session count of 2 reached"), so `gemma4-e5b-h41` and `gemma4-oracle-h41` launch, from the same built notebooks,
  when the first pair finishes. Deviation from "launch together", recorded here; it only affects time of day.
- 15:12 IST: `gemma4-e5b-h41` and `gemma4-oracle-h41` launched from the same built notebooks. All four runs: built
  from 61c7f8b, no uncommitted changes, 4 x L4, harness check OK, 41/41 tasks, no gold failures, no errors other
  than the session timeout (no task dropped).

#### Held-out results (2026-10-31, confirmatory, as pre-registered in A10)

Run: `python analysis/heldout_tests.py e2_h41 e3_1_h41 e5b_h41 oracle_h41` (analysis code unchanged since 352a0dd).
Output: `experiments/heldout_tests.json`. Solves: E2 14/41, E3.1 13/41, E5b 10/41, ORACLE 12/41.

| Claim | Result | Status |
|---|---|---|
| C1 /tmp compliance | E3.1 20/20 scratch-first under /tmp, E2 0/25; one-sided Fisher p = 3e-13 | **pass** |
| C2 structure raises source-first | E5b 11/41 vs E2 10/41; discordant b = 5, c = 4; one-sided McNemar p = 0.50; writers-only Fisher p = 0.37; localizer median 13.8 s (check met) | **fail** |
| C3 location bound | ORACLE - E2 = -4.9 pp, one-sided upper bound +2.4 pp; ORACLE wrong-files-only share 0.0 | **not tested** (sequence stopped at C2); reported as an estimate only |

Estimates (source-first difference, 95% bootstrap CI): E5b - E3.1 -4.9 pp [-22.0, +12.2]; E5b - ORACLE -2.4 pp
[-14.6, +9.8]; E3.1 - E2 +7.3 pp [-7.3, +22.0]. Per repo (E2 / E3.1 / E5b / ORACLE): FastAPI 4/5/6/7, Rich 6/8/5/5.

Reading: the agent follows a literal instruction (C1). The dev-set finding that a no-tool localizer makes the fixer
start with a source edit (dev: 24/44 writers) was **not replicated** on held-out tasks (11/31 writers); per the
pre-registration this is "not detected", with the estimate and CI above, not "no effect". The localizer did run
fast (manipulation check met), so the arm worked as designed; the fixer still wrote a scratch script first in 20
of 41 tasks. C3 is not claimed. Spare run (E5b r2 on heldout41) is available under A10; launch needs owner approval.
- Owner decision (2026-10-31): spare run **not used**. It could not change the C2 verdict (primary uses r1 only);
  quota is kept. No further runs for the paper; Draft 3 written from these results (`docs/paper/draft.md`, tables
  generated by `analysis/paper_tables.py`).

## 9. What is left to the builder

- Notebook mechanics: how variants are built and named (one Kaggle kernel per experiment is fine).
- Whether to set a sampling seed (it does not remove run-to-run variance from the sandbox; optional).
- Exact wording of prompt v2, drafted from the failure findings and reviewed before E3 runs.
- Updating `analysis/analyze_traces.py` to add paired comparison and context-crash counts.
