"""Checks for analysis/heldout_tests.py. Run: python analysis/test_heldout_tests.py"""

from heldout_tests import evaluate, valid_tasks


def row(solved=False, first='', tmp='', overlap='', finder=0.0, gold=True, error=''):
    return {'solved': solved, 'first': first, 'tmp': tmp, 'overlap': overlap, 'finder_seconds': finder,
            'gold': gold, 'error': error, 'repo': 'rich'}


def arms(n=20, e5b_source=15, e2_source=3, oracle_extra=0):
    """E2 starts with a repo-root script, E3.1 with a /tmp script, E5b mostly with source; ORACLE solves like E2."""
    e2 = {f't{i}': row(solved=i < 5, first='source' if i < e2_source else 'scratch',
                       tmp='' if i < e2_source else False) for i in range(n)}
    e31 = {f't{i}': row(solved=i < 5, first='source' if i < 4 else 'scratch',
                        tmp='' if i < 4 else True) for i in range(n)}
    e5b = {f't{i}': row(solved=i < 5, first='source' if i < e5b_source else '', finder=11.0) for i in range(n)}
    oracle = {f't{i}': row(solved=i < 5 + oracle_extra, first='source', overlap='all' if i >= 5 else '')
              for i in range(n)}
    return e2, e31, e5b, oracle


def test_all_three_claims_pass():
    r = evaluate(*arms())
    assert [r[c]['status'] for c in ('C1', 'C2', 'C3')] == ['pass', 'pass', 'pass']


def test_fixed_sequence_stops_at_first_failure():
    r = evaluate(*arms(e5b_source=3))             # E5b no better than E2: C2 fails
    assert r['C1']['status'] == 'pass' and r['C2']['status'] == 'fail'
    assert r['C3']['status'] == 'not tested (sequence stopped at C2)'


def test_no_write_counts_as_not_source_first():
    e2, e31, e5b, oracle = arms()
    r = evaluate(e2, e31, e5b, oracle)
    assert r['C2']['b'] == 12 and r['C2']['c'] == 0          # tasks 3-14: only E5b source-first; tasks 15-19: neither


def test_harness_failures_dropped_from_all_arms():
    e2, e31, e5b, oracle = arms()
    oracle['t0']['gold'] = False
    e5b['t1']['error'] = 'RuntimeError: sandbox crashed'
    e2['t2']['error'] = 'Agent exceeded session timeout (4.5 min)'      # a timeout is a normal outcome, kept
    assert set(valid_tasks([e2, e31, e5b, oracle])) == {f't{i}' for i in range(2, 20)}


def test_c3_bound_fails_when_oracle_clearly_better():
    r = evaluate(*arms(oracle_extra=8))
    assert r['C3']['status'] == 'fail' and r['C3']['upper'] >= 0.15


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
    print('all heldout_tests tests passed')
