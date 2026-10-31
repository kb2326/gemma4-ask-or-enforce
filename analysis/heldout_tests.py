"""The pre-registered tests for the held-out week (41 tasks), exactly as locked in the results log.

Usage:  python analysis/heldout_tests.py e2_h41 e3_1_h41 e5b_h41 oracle_h41
Reads experiments/<run>/results.csv and trace_stats.csv. Prints every test and writes heldout_tests.json.

Fixed-sequence testing C1 -> C2 -> C3, each at alpha 0.05; testing stops at the first failure, and later claims are
reported as not tested. Tasks where any arm hit a harness failure (gold patch fails here, or an error other than
the session timeout) are dropped from every paired comparison.
  C1 (manipulation check): among scratch-first tasks, E3.1 puts the script under /tmp in >= 80%, E2 in <= 20%,
     and one-sided Fisher p < 0.05.
  C2 (primary): per task, "first file write is a source edit" (no write = 0); E5b vs E2, one-sided exact McNemar
     p < 0.05. Sensitivity: writers-only one-sided Fisher. Manipulation check: E5b localizer median <= 60 s.
  C3: one-sided 95% upper bound (paired bootstrap) of the ORACLE minus E2 solve-rate difference < +15 pp.
     Manipulation check: share of ORACLE's unsolved tasks whose patch touched only wrong files.
  Estimates (no test): source-first differences E5b - E3.1, E5b - ORACLE, E3.1 - E2, with 95% CIs.
"""

import csv
import json
import statistics
import sys
from pathlib import Path

from compare import bootstrap_ci, bootstrap_upper, fisher_greater, mcnemar_greater

EXPERIMENTS = Path(__file__).resolve().parent.parent / 'experiments'
ALPHA = 0.05
TIMEOUT = 'Agent exceeded session timeout'


def load_arm(run):
    results = {r['instance_id']: r for r in csv.DictReader(open(EXPERIMENTS / run / 'results.csv', encoding='utf-8'))}
    stats = {r['task']: r for r in csv.DictReader(open(EXPERIMENTS / run / 'trace_stats.csv', encoding='utf-8'))}
    arm = {}
    for task, r in results.items():
        s = stats.get(task, {})
        arm[task] = {'solved': r['agent_resolved'] == 'True', 'gold': r['gold_resolved'] == 'True',
                     'error': r.get('error', ''), 'first': s.get('first_write_kind', ''),
                     'tmp': {'True': True, 'False': False}.get(s.get('first_write_in_tmp', ''), ''),
                     'overlap': s.get('patch_overlap', ''), 'finder_seconds': float(s.get('finder_seconds') or 0),
                     'repo': task.split('_')[0]}
    return arm


def valid_tasks(arms):
    """Tasks every arm ran without a harness failure (a session timeout is a normal outcome)."""
    common = set.intersection(*(set(a) for a in arms))
    return sorted(t for t in common
                  if all(a[t]['gold'] and (not a[t]['error'] or a[t]['error'].startswith(TIMEOUT)) for a in arms))


def source_first(r):
    return 1 if r['first'] == 'source' else 0


def estimate(new, old, tasks):
    diffs = [source_first(new[t]) - source_first(old[t]) for t in tasks]
    lo, hi = bootstrap_ci(diffs)
    return {'diff': round(sum(diffs) / len(diffs), 3), 'ci95': [round(lo, 3), round(hi, 3)]}


def evaluate(e2, e31, e5b, oracle):
    tasks = valid_tasks([e2, e31, e5b, oracle])
    out = {'tasks': len(tasks), 'dropped': sorted(set(e2) - set(tasks))}

    # C1: literal compliance with "put scratch scripts in /tmp".
    def tmp_counts(arm):
        scratch = [arm[t] for t in tasks if arm[t]['first'] == 'scratch']
        return sum(r['tmp'] is True for r in scratch), sum(r['tmp'] is not True for r in scratch)
    (a, b), (c, d) = tmp_counts(e31), tmp_counts(e2)
    p1 = fisher_greater(a, b, c, d)
    share31, share2 = a / max(a + b, 1), c / max(c + d, 1)
    out['C1'] = {'e31_tmp_share': round(share31, 3), 'e2_tmp_share': round(share2, 3), 'p': p1,
                 'passed': share31 >= 0.8 and share2 <= 0.2 and p1 < ALPHA}

    # C2: structure raises source-first (whole-task indicator, paired).
    bb = sum(source_first(e5b[t]) and not source_first(e2[t]) for t in tasks)
    cc = sum(source_first(e2[t]) and not source_first(e5b[t]) for t in tasks)
    p2 = mcnemar_greater(bb, cc)
    writers = lambda arm: [arm[t] for t in tasks if arm[t]['first']]
    w5, w2 = writers(e5b), writers(e2)
    sens = fisher_greater(sum(map(source_first, w5)), sum(1 - source_first(r) for r in w5),
                          sum(map(source_first, w2)), sum(1 - source_first(r) for r in w2))
    finder = statistics.median(e5b[t]['finder_seconds'] for t in tasks)
    out['C2'] = {'b': bb, 'c': cc, 'p': p2, 'passed': p2 < ALPHA,
                 'e5b_source_first': sum(source_first(e5b[t]) for t in tasks),
                 'e2_source_first': sum(source_first(e2[t]) for t in tasks),
                 'sensitivity_writers_fisher_p': sens, 'localizer_median_s': finder,
                 'localizer_check': finder <= 60}

    # C3: giving the location does not raise solves by 15 pp or more.
    diffs = [int(oracle[t]['solved']) - int(e2[t]['solved']) for t in tasks]
    upper = bootstrap_upper(diffs)
    unsolved = [oracle[t] for t in tasks if not oracle[t]['solved']]
    out['C3'] = {'diff': round(sum(diffs) / len(diffs), 3), 'upper': round(upper, 3), 'passed': upper < 0.15,
                 'oracle_wrong_files_only_share': round(sum(r['overlap'] == 'none' for r in unsolved)
                                                        / max(len(unsolved), 1), 3)}

    stopped = None
    for claim in ('C1', 'C2', 'C3'):
        if stopped:
            out[claim]['status'] = f'not tested (sequence stopped at {stopped})'
        else:
            out[claim]['status'] = 'pass' if out[claim]['passed'] else 'fail'
            stopped = None if out[claim]['passed'] else claim

    out['estimates'] = {'E5b-E3.1': estimate(e5b, e31, tasks), 'E5b-ORACLE': estimate(e5b, oracle, tasks),
                        'E3.1-E2': estimate(e31, e2, tasks)}
    out['per_repo_source_first'] = {repo: {name: sum(source_first(arm[t]) for t in tasks if arm[t]['repo'] == repo)
                                           for name, arm in (('E2', e2), ('E3.1', e31), ('E5b', e5b), ('ORACLE', oracle))}
                                    for repo in sorted({e2[t]['repo'] for t in tasks})}
    return out


if __name__ == '__main__':
    runs = sys.argv[1:5]
    result = evaluate(*(load_arm(r) for r in runs))
    print(json.dumps(result, indent=1))
    (EXPERIMENTS / 'heldout_tests.json').write_text(json.dumps({'runs': runs, **result}, indent=1) + '\n')
