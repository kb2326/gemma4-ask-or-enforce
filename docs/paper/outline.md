# Paper outline (Paper Track, due 2026-11-12 23:59 UTC)

Status: skeleton, 2026-10-24. Slots marked **[pending: run]** fill in as results arrive. Exploratory results are
labelled as such; only predictions committed before a run count as confirmatory.

## Constraints from the official pages (read 2026-10-24)

- Kaggle Writeup, **3,000 words maximum**, original unpublished research; non-archival.
- Required parts: abstract, introduction, research description (methods and experiments), related work and
  citations. Optional: a public Kaggle notebook (Project Links) and other public links.
- Judged equally on: **Novelty** (new insight into existing methods counts), **Quality** (does it generalize beyond
  this competition), **Relevance** (impact on agentic software engineering), **Verifiability** (enough detail to
  understand how data was obtained, analysed and interpreted), **Clarity**.
- Suggested topics include Code Comprehension and Graph Reasoning; our graph-vs-grep result belongs there.
- **Data rule (Rules §4a):** we may use the Competition Data for research, but must **not publish or redistribute**
  it outside the competition. So the writeup and any public repo carry **no task files, gold patches, problem
  statements, graphs, raw transcripts, or files derived from gold patches** (e.g. `experiments/oracle/hints.json`).
  What we can publish: our code, configs and prompts; task IDs with our own per-task numbers; aggregate statistics;
  short paraphrased examples. Reproduction goes through a **public Kaggle notebook** that reads the Competition
  Data inside Kaggle, where only participants can run it.

## Working title

"Ask or Enforce? Prompt Rules vs. Agent Structure for a Small Open Model under a Fixed Budget"

## One-sentence thesis (revised 2026-10-24 after the code-review correction)

For a small open model under a fixed per-task budget, a behaviour rule in the prompt is followed only in its
literal, checkable part, while the same intent built into the agent's structure changes behaviour significantly
(though not completely), and limits that are left to the prompt are ignored until made structural; and the binding
bottleneck is producing a correct fix within the budget, not finding the code.

## Claims and evidence (corrected definitions: source = package file, not repo-root/test/repro/tmp)

| # | Claim | Evidence | Status |
|---|---|---|---|
| C1 | Asking is followed literally, not in intent | E3.1 put scratch scripts in /tmp as told, but source-first rose only 26% → 38% (18/70 vs 19/50, Fisher p = 0.17) | dev set, 2 runs |
| C2 | Enforcing changes behaviour; limits left to the prompt are ignored until structural | pipeline arms source-first 34/57 (60%) vs 26%, p = 0.0001 (E5b alone p = 0.003); E5 localizer told "about 8 calls" took 177 s of 231; tool-less localizer 11 s; fixer still scripts first on ~40% | dev set, 3 runs |
| C3 | Finding is not the bottleneck under the budget | ORACLE 27/60 vs 36/90; wrong-file failures 0 in both runs (E2: 3); never-edited 11 → 6, 9 | dev set, 2 runs; hints' function names wrong on ~4 tasks (files always right) |
| C4 | Graph search from issue names weaker than grep, complementary | 8/30 vs 11/30, union 15/30 | done (exploratory) |
| C5 | Held-out confirmation | **[pending: Oct 31 week, re-approve predictions]** | — |
| — | Withdrawn | "the prompt rule backfired (30 of 50 scratch-first vs 0)": measurement artifact, see results-log correction | — |

## Section plan (word budget ≈ 2,900)

1. **Abstract** (150): thesis, setting, the three main numbers, one limitation.
2. **Introduction** (350): small open models in agentic SWE; the only levers in this competition are prompts and
   structure (declarative ADK YAML, no code); question: ask or enforce? Contributions list (C1-C4).
3. **Setting** (350): Gemma 4 31B W4A16 on 4x L4, vLLM, 32k context; the model is never trained: all runs use the
   official sample submission's two small LoRA adapters unchanged (stated for verifiability); harness tools; 4.5-minute / 100-call budget
   per task; framed as a fixed budget, all results also in steps and tokens. Task set: 71 of 129 practice tasks
   validated (gold passes, empty fails, three repeats); 30 dev, 30 held-out (seeded).
4. **Method** (500): arms (E2, E3.1, E5, E5b, ORACLE, graph probe) with one-line diffs; measurements from
   transcripts (first-write kind, no-source-edit, localization hit vs gold files, stage time, nudges); statistics
   (exact McNemar, task bootstrap CI, pooled reference over identical runs, replicates); pre-registration.
5. **Results** (800):
   - Table 1: arms × solved, timeouts, first-write source share, no-source-edit, stage-1 share of time.
   - Table 2: failure shift E2 → ORACLE → E5 (never edited / wrong files / right file wrong fix).
   - Figure 1: time split per task, stage 1 vs stage 2 (E5 vs E5b).
   - Graph vs grep probe (C4).
   - Held-out confirmation (C5).
6. **Related work** (350): Agentless; SWE-agent; SWE-Gym; AgentIF; "On the Clock"; Budget-Aware Tool-Use; SWE-Effi;
   LocAgent, CodexGraph, RepoGraph; SHERLOC; Miller 2024 (error bars).
7. **Limitations** (250): n = 30, few runs (only large effects detectable); E5b chosen after seeing E5 (its choice is
   exploratory, its predictions were pre-registered); E5 differs from E2 in more than the split (helper removed,
   rarely used); practice repos are not the hidden ones; one model; symbol extraction heuristic in the probe.
8. **Conclusion and practical advice** (150): for anyone configuring a small-model agent: enforce with structure,
   budget each stage structurally, spend the budget on fixing. One sentence of future work only: training (e.g. Kimi-Dev's
   staged training) may build the habits prompts could not enforce. Training/LoRA is out of scope for this paper.

## Verifiability assets

- Public GitHub repo (kb2326) after removing competition-derived files from history or publishing a clean copy:
  analysis code with tests, notebook builder, agent configs and prompts, pre-registration log.
- Public Kaggle notebook that rebuilds the arms and recomputes the tables from the Competition Data on Kaggle.
- Per-task results table (task IDs, solved, timeouts, first-write kind), no task content.

## Open items

- [ ] Fill C1-C3 after runs 3-6; C5 after the Oct 31 week.
- [ ] Decide clean-copy vs history rewrite for the public repo (hints.json, saved patches contain repo code).
- [ ] Ask on the forum whether short transcript excerpts of practice tasks count as Competition Data.
- [ ] Figure 1 script.
