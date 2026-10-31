# E5 / E6 design: structure vs prompt for a small open model under a time limit

Date: 2026-10-19. Status: APPROVED by owner 2026-10-23. Parent plan: `2026-10-18-experiment-plan-design.md`
(rules, decision rule, amendments A1-A8 still apply unless this document says otherwise).

## 1. Intent and why

E5 and E6 are the novel part of this project and the core of the paper (Paper Track deadline Nov 12). They must be
designed to research standard before any GPU is spent: question first, hypotheses and decision rules committed before
launch, mechanism measured from traces, every GPU run named here in advance.

What we already know (from our own runs):

- Prompt rules did not change behaviour. E3/E3.1 told Gemma to edit source by step 8; it still wrote `/tmp`
  reproduction scripts first (21 and 17 of 30 tasks) and edited later than the official prompt (median 141 s / 125 s
  vs 84 s). Scores rose (14, 15 vs 11-13) but not through the rule.
- Time is the main failure: 12-15 of 30 tasks time out at 4.5 min; ~9.5 s per step, ~18-20 steps median.
- Finding the code is a large share of failures. Among failed tasks per run (15-19): ~40% end with no source edit,
  ~30% edited the wrong files, ~25% edited the right files but the fix was wrong (file-level, from saved patches).
- The harness's graph tools are almost never used: across 185 traces, `search_similar_code` 12 calls,
  `get_code_neighbors` 4, `get_code_subgraph` 0. The helper sub-agent was called once (and overflowed its context).

What the literature says (full review in this session; key sources):

- No paper compares the same model and same tools as a single agent vs a staged pipeline; published staging gains are
  confounded with new tools, sampling or validation (Agentless 2407.01489, SWE-Adept 2603.01327, Kimi-Dev 2509.23045).
- Fixed workflows beat free agents for open-weight models, attributed to a constrained action space (SWE-Gym
  2412.21139, ICML 2025), but compliance is never measured. Agents follow prompt-stated constraints poorly
  (AgentIF 2505.16944).
- Graph tools help strong or fine-tuned models modestly; untuned open models under-use or misuse them (LocAgent
  2503.09089, CodexGraph 2408.03910, RepoGraph 2410.14684). LocAgent's ablation: removing keyword search costs ~18
  points, removing graph traversal 2-5 points.
- Injected localization helps small and mid-size models most (SHERLOC 2606.24820).
- Statistics with small n: paired per-task comparisons, task bootstrap, replicates (Miller 2411.00640).
- Practical example of "rules in the prompt vs machinery that enforces them": github.com/FareedKhan-dev/lean-agent
  (course notebook, not peer-reviewed; cite as an example only).

## 2. Research questions and pre-registered hypotheses

- **RQ1 (E5, structure vs prompt).** For Gemma 4 31B under a 4.5-minute budget, does enforcing "find, then fix"
  through agent structure change behaviour where the same intent stated in the prompt (E3.1) did not?
  - H1a (mechanism, primary): **compliance with "no scratch scripts before the first source edit"**, the exact
    intent E3.1 stated in its prompt. Metric: share of tasks whose first file write (any `write_file`/`edit_file`,
    or a shell redirect creating a file) is a source edit rather than a `/tmp` scratch file, among tasks with any
    write. Prediction: E5 (fixer) is at least 25 points higher than E3.1, in both E5 replicates. Comparable
    across arms because it does not depend on where the clock starts. *(Builder-check answer, my call: a time-based
    primary would either be near-impossible from task start or near-automatic from fixer start.)*
  - H1a' (secondary, reported both ways): time to first source edit measured from task start (end-to-end, the
    number that matters under the 4.5-minute limit) and from fixer start. No threshold; reported with CIs.
  - H1b: tasks ending with no source edit are no higher than E2 (6), in both replicates.
  - H1c (outcome, secondary): resolve rate. Reported with paired tests; claimed only if the pooled paired test
    supports it (expected to be underpowered).
- **RQ2 (oracle, is localization the bottleneck?).** If the agent is told the correct files and functions, how much
  does the current agent (E2) improve?
  - H2: oracle solves more than E2's pooled reference; the gap is the ceiling for any localization improvement.
    **Gap = ORACLE solved minus 12** (the mean of the three E2-style runs: 11, 12, 13). If ORACLE r1 solves 14 or
    fewer (gap under 3), E6 is deprioritized for this week. *(My call. One run sits inside the noise band, so this
    is a scheduling rule only; the paper claim about the bottleneck needs ORACLE r2.)*
- **RQ3 (E6, graph tools).** Does a small untuned model use graph tools when a dedicated stage requires them, and does
  that localize better?
  - H3a: a graph-centred localizer makes graph calls in most tasks (compared with ~0 today).
  - H3b (prediction from LocAgent, stated so it can fail): file-level localization accuracy of the graph-only
    localizer is not higher than E5's localizer (which has `run_command` for grep). If H3b is refuted, that is a
    finding.

## 3. Arms

All arms use the kept E2 settings (31B W4A16, temperature 0.2, `max_output_tokens` 8192, thinking 4096 with
`include_thoughts`, `eval_config` unchanged) unless stated. The practice set is `experiments/practice30.json`.

| Arm | What changes from E2 | Purpose |
|---|---|---|
| **E2** (have 1 run; run 1 and E0 are near-identical) | — | Baseline |
| **E3.1** (have 1 run) | Prompt v2.1 | Prompt-only control: same intent as E5, delivered by prompt |
| **ORACLE** | E2 + `hints_text` set to the gold source files and functions | Ceiling for localization (practice only, never submitted) |
| **E5** | `SequentialAgent`: localizer → fixer | Structure |
| **E6** | E5 with a graph-centred localizer | Graph tools |

E5 details (validated offline; skeleton in the session scratchpad `e5/`):

- Root `agent_class: SequentialAgent`, sub-agents `localizer` then `fixer`, same model and adapter (`main_lora`) for
  both to avoid an adapter confound (the sample used `tool_lora` for its helper; switching is out of scope).
- Localizer tools: `read_file`, `run_command`, `search_similar_code`, `get_code_neighbors`, `get_code_subgraph`.
  No edit tools: it cannot edit, which is the structural enforcement. `output_key: localization`.
  Prompt: find the files and functions to change, stop within about 8 tool calls, reply with a short plain-text
  list of locations and a one-line plan. No braces in prompts except the optional templates below.
- Fixer tools: exactly E2's root tools minus the helper: `run_command`, `read_file`, `edit_file`, `write_file`,
  `get_status`, `submit_patch`, `get_code_neighbors`, `search_similar_code`, `get_code_subgraph`. *(My call: keeps
  the fixer identical to E2's agent apart from the handed-over findings.)* Removing the helper is intended: it was
  called once in 185 traces and overflowed, so it is a near no-op; recorded as a second, minor difference.
- The localizer's length is controlled only by its prompt: the harness has no per-agent tool or time cap (budgets
  are shared per task). What structure guarantees is that the localizer **cannot edit** and the fixer starts after
  it. The localizer's share of time is measured and reported as a limitation.
  `include_contents: default`, so it keeps the harness task message (instructions 0-5, budget lines) and its own
  memory after a nudge. Prompt: the official sample prompt plus a short preamble "the localizer's findings are above;
  start by editing those locations", and must end with `submit_patch`.
- Same thinking budget (4096) for both stages: one structural change, not a sampling change.

E6 details: identical to E5 except the localizer's tools are `read_file`, `search_similar_code`, `get_code_neighbors`,
`get_code_subgraph` (no `run_command`), and its prompt tells it to start from symbol names in the issue.

ORACLE details: in the practice notebook only, write a modified copy of `tasks.jsonl` whose `hints_text` lists the
gold patch's source files and changed functions (no code, no line numbers). The harness adds it to the prompt as
"## Hints" (`swegemma/harness/agent_runner.py:381-383`). The submission is unchanged E2.

## 4. Measurements (all from traces, computed by `analysis/`)

Existing: solved, timeouts, steps, seconds, `first_edit_or_end_s`, no-source-edit count, scratch writes, tool calls.
New (to build offline before any run):

- Gold locations per task: source files and changed functions from the gold patch, excluding docs/tests.
- File-level localization: the localizer's reply (E5/E6), and for single agents the files edited; "hit" only if
  all gold files are covered; also recall. Function level where the gold patch modifies an existing function.
- Resolve rate given correct file-level localization.
- Per-stage time and tool calls (localizer vs fixer, by event author).
- Nudges (harness continuation messages) and whether the localizer re-ran after a nudge.
- Graph-tool calls per task.
- Real compaction detection (replace the `'previous agent'` text heuristic in `analyze_traces.py:62`, which does not
  detect ADK compaction events).

Statistics: `analysis/compare.py` (exact McNemar, task bootstrap) on each run pair; for replicated arms, per-task
solve fraction and a paired bootstrap of the mean difference, also reported per repo. With n=30, only large effects
are detectable; the paper reports that power limit.

## 5. Offline gates (no GPU; must pass before the matching GPU run)

- **G1 · build check** (local venv in the scratchpad): `validate_directory`, `discover_declared_models`,
  `compile_submission` pass for E5 and E6; the mock-LLM simulation confirms `{localization?}` reaches the fixer.
- **G2 · nudge behaviour** (local simulation): measure what happens when the fixer stops without submitting. Known:
  ADK restarts the `SequentialAgent` from the localizer. Accept if the localizer's re-run is short in simulation;
  record the risk otherwise. Nudge counts are then measured in the real run.
- **G3 · graph probe** (free Kaggle CPU notebook, no vLLM): call `search_similar_code` with symbol names taken from
  each issue on the 30 practice tasks; measure whether the gold file appears in the top 5, and compare with
  `grep -rl` on the same keywords. **Pass: graph top-5 file hit rate at least grep's.**
  - Pass: E6 runs graph-only as designed (H3a, H3b as written).
  - Fail: the only other search in the harness is `run_command` (9 tools total), so E6 becomes "graph-first":
    E5's tools plus a prompt that requires graph calls before any grep. RQ3 is then restated before launch as
    "does a dedicated graph-first stage make the model use graph tools (H3a), and does that change localization
    accuracy vs E5?"; H3b is dropped, and G3's own result (graph search loses to grep on these repos) is reported
    as the RQ3 evidence. *(My call.)*
- **G4 · analysis ready**: the new metrics in section 4 run on the existing E2 and E3.1 traces and the numbers above
  (no-edit / wrong-file / right-file) reproduce.
- Housekeeping before the first GPU run: pin the wheelhouse dataset version in every kernel-metadata.

## 6. GPU schedule (one run = about 4.3 h of the 30 h weekly quota)

Week of Oct 24 (6 runs, about 26 h; about 4 h held back for one failed-run retry; leaderboard submissions use no quota):

| # | Run | Condition to launch |
|---|---|---|
| 1 | E5 r1 | G1, G2, G4 pass |
| 2 | ORACLE r1 | G4 passes |
| 3 | E3.1 r2 (prompt-only control replicate) | — |
| 4 | E5 r2 | run 1 completed without harness failure |
| 5 | E6 r1, or E5 r3 if H2's gap is under 3 tasks | G3 passed (variant fixed by G3) |
| 6 | E6 r2, or ORACLE r2 if E6 was dropped | — |

Week of Oct 31 (before the paper): E2 r2 (baseline replicate), held-out pair (E2 and the best kept version, back to
back, A1), plus up to 3 replicates chosen by a rule committed before that week starts.

Frozen baseline: for this week every arm builds on E2, even if E3.1 r2 leads to adopting prompt v2.1 for the
submission. Adoption changes what is submitted, not this week's comparisons. *(My call; deviation from the parent
plan's "build on the latest adopted version", recorded here so comparisons stay fixed.)*

If E5's localizer prompt must be revised after r1 (stop rule in section 7), the revised version is a new arm
(E5b) and does not count as an E5 replicate. **Owner decision (2026-10-23): yes. Confirming E5/E5b takes priority; if E5b needs its second run, it takes run 5 and E6 moves to the Oct 31 week if needed.**

No other GPU runs. Every launch needs: this row's condition met, its hypothesis line in the results log committed,
and the owner's "yes" in chat.

## 7. Decision rules

- **Adoption for submission** (unchanged from the parent plan): rule (a) net +3 against the pooled reference, or
  rule (b) the targeted metric beats the identical-run spread (A3). E5's targeted metric is time-to-first-source-edit
  and no-source-edit count.
- **Paper claims** are separate from adoption: H1a/H1b/H3a can be claimed from trace metrics even if resolve rate
  does not move; resolve-rate claims need the pooled paired test.
- **Stop rules:** a run with harness-level failures on more than 3 tasks (e.g. empty patches from crashes) is
  re-run once after a fix and does not count. If E5 r1 shows the localizer consuming over half the time budget on
  median, E5 r2 uses a revised localizer prompt (committed before launch) rather than a straight replicate.

## 8. Goals, non-goals, anti-goals

- Goals: a clean, replicated answer to RQ1-RQ3; the measurement code to support it; a submission decision for the
  best kept version.
- Non-goals: a review/validation third stage, model swaps (12B), LoRA training, tuning on held-out tasks.
- Anti-goals: GPU runs not listed in section 6; repo-specific prompt content; claims about the hidden leaderboard
  from practice tasks; training on Claude/GPT outputs; publishing task data before the data rules are checked.

## 8b. Paper framing note (owner discussion, 2026-10-24)

Wall-clock seconds depend on hardware, so the paper frames the constraint as a fixed per-task budget and reports
every result in seconds, agent steps and tokens. Claims are stated for "a fixed budget", with the competition's
4.5-minute limit on 4x L4 as the concrete instance. Related budget work: SWE-agent cost limits, OpenHands /
mini-SWE-agent step limits, Budget-Aware Tool-Use (2511.17006), SWE-Effi (2509.09853), "On the Clock" (2026).

## 9. Left to the builder

- Exact wording of the localizer and fixer prompts (reviewed by the owner before G1; no braces except the optional
  `{localization?}` / `{problem_description}` templates).
- Format of the localizer's reply (plain text list; parsing must be tolerant).
- How the notebooks build the ORACLE task file and new kernels (`gemma4-e5`, `gemma4-oracle`, `gemma4-e6`, `-r2`).
