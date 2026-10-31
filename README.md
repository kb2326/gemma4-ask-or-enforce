# gemma4-ask-or-enforce

Code, configs and the pre-registered experiment log behind the paper *Ask or Enforce? A Pre-Registered Test of
Prompt Rules and Agent Structure for a Small Open Model under a Fixed Budget*, written for the Kaggle
[Gemma 4 Developer Agent Competition](https://www.kaggle.com/competitions/gemma-4-developer-agent) Paper Track.

The task: configure a Gemma 4 31B agent (declarative Google ADK YAML + prompts, no training) that fixes real GitHub
issues, graded by hidden tests, within 4.5 minutes and 100 tool calls per task.

## Findings in brief

Designed on 30 development tasks, then tested once on 41 held-out tasks with the tests and analysis code committed
beforehand (`docs/superpowers/specs/2026-10-18-experiment-plan-design.md`, amendment A10).

| Pre-registered claim | Held-out result |
|---|---|
| C1: a literal prompt rule ("put scratch scripts in /tmp") is followed | **pass**, 20/20 vs 0/25 (p < 0.001) |
| C2: a tool-less localizer stage makes the fixer start with a source edit more often | **fail**, 11/41 vs 10/41 (p = 0.50); the development-set effect did not replicate |
| C3: handing over the correct files raises solves by less than 15 pp | not tested (sequence stopped at C2); estimate -4.9 pp |

Solved on held-out tasks: reference 14/41, prompt rule 13/41, tool-less localizer 10/41, correct files given 12/41.
A time limit written in a stage's prompt was ignored (median 177 s), while removing that stage's tools enforced it
(11-14 s) in every run. Full tables: `docs/paper/tables.md`; paper draft: `docs/paper/draft.md`.

## What is (and is not) in this repository

The competition rules (section 4a) do not allow redistributing the Competition Data, so this repository holds only
our own work. Not included, and rebuilt locally from the competition data instead:

- the official sample submission (prompt, agent YAML, adapter configs);
- task statements, gold patches, graphs, agent transcripts and agent patches;
- anything derived from gold patches (e.g. ORACLE hints);
- generated notebooks, which embed the above.

`python tools/check_public.py` verifies the committed tree contains none of these.

## Layout

| Path | What it is |
|---|---|
| `submission/` | Our changes to the official sample (sampling and per-task budget). The builder lays them over the sample. |
| `experiments/<arm>/submission/` | Agent configs and prompts for each arm (E5, E5b, E6). `<<OFFICIAL SAMPLE PROMPT>>` marks where the builder inserts the official prompt. |
| `experiments/<run>/results.csv`, `trace_stats.csv` | Per-task outcomes and transcript measurements (task IDs and our own numbers only). `*_h41` are the held-out runs. |
| `experiments/practice30.json`, `heldout41.json` | Development and held-out task IDs. |
| `experiments/heldout_tests.json` | Output of the pre-registered held-out tests. |
| `analysis/` | Transcript measurements, gold-location extraction, statistics, held-out tests and paper tables; each module has a `test_*.py`. |
| `notebooks/build_notebooks.py` | Builds every Kaggle notebook (`--arm <name>` for one arm). |
| `tools/` | Offline checks: competition validator (`check_submission.py`), pipeline simulation (`sim_pipeline.py`), publishability check (`check_public.py`). |
| `docs/superpowers/specs/` | Experiment plan, E5/E6 design, and the results log: every prediction committed before its run, the post-review correction, amendment A10 and the held-out results. |
| `docs/paper/` | Paper outline, draft and generated tables. |
| `guide/` | Learning guide and field notes (HTML). |

## Reproducing

1. Join the competition and download its data into `data/agent/` (tasks, sample submission, harness README) and the
   harness wheels into `data/harness/`. `data/` is git-ignored.
2. Offline checks (Python 3.12+): `sh tools/setup_harness_venv.sh`, then
   `.venv-harness/Scripts/python tools/check_submission.py submission experiments/e5/submission`, and in
   `analysis/` run each `python test_*.py`.
3. ORACLE hints: `python analysis/gold.py hints` and `python analysis/gold.py hints heldout41` (local only).
4. Build and run an arm on Kaggle (4x L4): `python notebooks/build_notebooks.py --arm e5b_h41`, then
   `kaggle kernels push -p notebooks/e5b_h41 --accelerator NvidiaL4`.
5. Analyse a finished run: `python analysis/analyze_traces.py data/runs/<kernel>/results`, copy `results.csv` and
   `trace_stats.csv` into `experiments/<arm>/`.
6. Held-out tests: `python analysis/heldout_tests.py e2_h41 e3_1_h41 e5b_h41 oracle_h41`. Paper tables:
   `python analysis/paper_tables.py` (also fills the tables in `docs/paper/draft.md`).

Kaggle API token: put `KAGGLE_API_TOKEN=...` in `.env` (git-ignored).
