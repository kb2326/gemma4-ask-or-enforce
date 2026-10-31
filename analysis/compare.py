"""Paired comparison of agent runs on the same task set, with uncertainty.

Usage:
  python analysis/compare.py e0 practice30-baseline          # one run vs one run
  python analysis/compare.py e3 --ref practice30-baseline e0 e2  # one run vs a pooled reference
  python analysis/compare.py --matrix practice30-baseline e0 e2 e1 e3   # per-task solve rates

Runs are folders under experiments/ holding results.csv (instance_id, agent_resolved, ...).
Statistics:
  - exact McNemar test (two-sided binomial on the discordant tasks)
  - task-level bootstrap 95% CI for the difference in solve rate (paired, seeded)
"""

import argparse
import csv
import random
from math import comb
from pathlib import Path

EXPERIMENTS = Path(__file__).resolve().parent.parent / 'experiments'
BOOTSTRAP_SEED = 20261019
BOOTSTRAP_N = 10000


def load(run):
    with (EXPERIMENTS / run / 'results.csv').open(encoding='utf-8') as f:
        return {r['instance_id']: r['agent_resolved'].strip().lower() == 'true' for r in csv.DictReader(f)}


def mcnemar_exact(b, c):
    """Two-sided exact McNemar p-value: binomial test of b vs c with p = 0.5."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def fisher_exact(a, b, c, d):
    """Two-sided Fisher exact test for the 2x2 table [[a, b], [c, d]] (sum of tables no more likely than observed)."""
    row, col, n = a + b, a + c, a + b + c + d

    def prob(x):
        return comb(row, x) * comb(n - row, col - x) / comb(n, col)

    observed = prob(a)
    lo, hi = max(0, col - (n - row)), min(row, col)
    return min(1.0, sum(p for x in range(lo, hi + 1) if (p := prob(x)) <= observed * (1 + 1e-9)))


def mcnemar_greater(b, c):
    """One-sided exact McNemar p-value that the new arm is better: P(X >= b), X ~ Bin(b + c, 0.5).

    b = tasks where only the new arm has the property, c = tasks where only the reference has it."""
    n = b + c
    return sum(comb(n, i) for i in range(b, n + 1)) / 2 ** n if n else 1.0


def fisher_greater(a, b, c, d):
    """One-sided Fisher exact p-value that row 1's share a/(a+b) exceeds row 2's c/(c+d): P(X >= a)."""
    row, col, n = a + b, a + c, a + b + c + d
    return sum(comb(row, x) * comb(n - row, col - x) for x in range(a, min(row, col) + 1)) / comb(n, col)


def bootstrap_means(diffs, n, seed):
    rng = random.Random(seed)
    k = len(diffs)
    return sorted(sum(diffs[rng.randrange(k)] for _ in range(k)) / k for _ in range(n))


def bootstrap_ci(diffs, n=BOOTSTRAP_N, seed=BOOTSTRAP_SEED):
    """95% percentile CI of the mean of per-task differences, resampling tasks."""
    means = bootstrap_means(diffs, n, seed)
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def bootstrap_upper(diffs, n=BOOTSTRAP_N, seed=BOOTSTRAP_SEED):
    """One-sided 95% upper bound of the mean per-task difference (95th percentile of the bootstrap means)."""
    return bootstrap_means(diffs, n, seed)[int(0.95 * n) - 1]


def pair(new, old):
    a, b = load(new), load(old)
    ids = sorted(set(a) & set(b))
    gained = [i for i in ids if a[i] and not b[i]]
    lost = [i for i in ids if b[i] and not a[i]]
    diffs = [int(a[i]) - int(b[i]) for i in ids]
    return {'tasks': len(ids), 'new_solved': sum(a[i] for i in ids), 'old_solved': sum(b[i] for i in ids),
            'gained': gained, 'lost': lost, 'p_mcnemar': mcnemar_exact(len(gained), len(lost)),
            'diff': sum(diffs) / len(ids), 'ci95': bootstrap_ci(diffs)}


def versus_reference(new, refs):
    a = load(new)
    ref = [load(r) for r in refs]
    ids = sorted(set(a).intersection(*ref))
    rate = {i: sum(r[i] for r in ref) / len(ref) for i in ids}
    gains = [i for i in ids if a[i] and rate[i] == 0]
    losses = [i for i in ids if not a[i] and rate[i] == 1]
    diffs = [int(a[i]) - rate[i] for i in ids]
    return {'tasks': len(ids), 'new_solved': sum(a[i] for i in ids), 'ref_mean_solved': sum(rate.values()),
            'gains': gains, 'losses': losses, 'flaky': [i for i in ids if 0 < rate[i] < 1],
            'diff': sum(diffs) / len(ids), 'ci95': bootstrap_ci(diffs)}


def matrix(runs):
    data = [load(r) for r in runs]
    ids = sorted(set(data[0]).intersection(*data[1:]))
    rows = sorted(((sum(d[i] for d in data), i, ''.join('X' if d[i] else '.' for d in data)) for i in ids), reverse=True)
    print(f'{"task":<16}{"marks":<{len(runs) + 2}}rate   (columns: {" ".join(runs)})')
    for n, i, marks in rows:
        print(f'{i:<16}{marks:<{len(runs) + 2}}{n}/{len(runs)}')
    counts = {k: sum(1 for n, _, _ in rows if n == k) for k in range(len(runs) + 1)}
    print('tasks by times solved:', counts)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('runs', nargs='*')
    p.add_argument('--ref', nargs='+')
    p.add_argument('--matrix', nargs='+')
    args = p.parse_args()
    if args.matrix:
        matrix(args.matrix)
    elif args.ref:
        r = versus_reference(args.runs[0], args.ref)
        print(f"{args.runs[0]} vs pooled {args.ref}: solved {r['new_solved']}/{r['tasks']} "
              f"(reference mean {r['ref_mean_solved']:.1f})")
        print(f"gains {r['gains']}  losses {r['losses']}  net {len(r['gains']) - len(r['losses'])}  flaky {len(r['flaky'])}")
        print(f"difference in solve rate {r['diff']:+.3f}, 95% CI [{r['ci95'][0]:+.3f}, {r['ci95'][1]:+.3f}]")
    else:
        r = pair(args.runs[0], args.runs[1])
        print(f"{args.runs[0]} vs {args.runs[1]}: {r['new_solved']} vs {r['old_solved']} of {r['tasks']}")
        print(f"gained {r['gained']}  lost {r['lost']}  exact McNemar p = {r['p_mcnemar']:.3f}")
        print(f"difference in solve rate {r['diff']:+.3f}, 95% CI [{r['ci95'][0]:+.3f}, {r['ci95'][1]:+.3f}]")


if __name__ == '__main__':
    main()
