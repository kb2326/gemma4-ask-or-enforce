"""Checks for analysis/compare.py. Run: python analysis/test_compare.py"""

from compare import (bootstrap_ci, bootstrap_upper, fisher_exact, fisher_greater, mcnemar_exact, mcnemar_greater,
                     pair)


def test_one_sided_tests():
    """Held-out primary tests are one-sided (direction fixed in advance)."""
    assert abs(mcnemar_greater(8, 0) - 0.5 ** 8) < 1e-12          # P(X >= 8), X ~ Bin(8, 0.5)
    assert abs(mcnemar_greater(0, 8) - 1.0) < 1e-12
    assert abs(mcnemar_greater(11, 2) - sum(__import__('math').comb(13, k) for k in range(11, 14)) / 2 ** 13) < 1e-12
    assert fisher_greater(10, 0, 0, 10) < 1e-4 and fisher_greater(0, 10, 10, 0) > 0.999
    assert fisher_greater(5, 5, 5, 5) > 0.5


def test_bootstrap_upper_is_one_sided_95():
    diffs = [1, 0, 0, -1, 0, 1, 0, 0, 0, 0]
    up = bootstrap_upper(diffs, n=4000)
    assert bootstrap_upper(diffs, n=4000) == up                    # seeded
    assert up < bootstrap_ci(diffs, n=4000)[1] + 1e-9              # one-sided 95% bound sits inside the two-sided 95% CI
    assert bootstrap_upper([0] * 20, n=500) == 0.0


def test_fisher_exact_known_values():
    """Two-sided Fisher exact test on a 2x2 table [[a, b], [c, d]]."""
    assert abs(fisher_exact(18, 52, 19, 31) - 0.166) < 0.002     # dev set: E3.1 vs reference, source-first
    assert abs(fisher_exact(34, 23, 18, 52) - 0.0001) < 0.0001    # dev set: pipeline vs reference
    assert fisher_exact(5, 5, 5, 5) == 1.0
    assert abs(fisher_exact(3, 1, 1, 3) - fisher_exact(1, 3, 3, 1)) < 1e-12
    assert fisher_exact(10, 0, 0, 10) < 0.0001


def test_mcnemar_known_values():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(2, 1) == 1.0                      # 3 discordant tasks can never be significant
    assert abs(mcnemar_exact(8, 0) - 2 / 256) < 1e-12      # 8 vs 0: p = 2 * 0.5^8
    assert abs(mcnemar_exact(0, 8) - mcnemar_exact(8, 0)) < 1e-12


def test_bootstrap_is_seeded_and_sane():
    diffs = [1, 0, 0, -1, 0, 1, 0, 0, 0, 0]
    assert bootstrap_ci(diffs, n=2000) == bootstrap_ci(diffs, n=2000)
    lo, hi = bootstrap_ci(diffs, n=2000)
    assert lo <= 0.1 <= hi and lo < 0 < hi
    assert bootstrap_ci([0] * 10, n=500) == (0.0, 0.0)


def test_e0_vs_run1_matches_hand_count():
    """E0 repeated the unchanged baseline: hand count was 2 gained, 1 lost, 12 vs 11."""
    r = pair('e0', 'practice30-baseline')
    assert (r['new_solved'], r['old_solved'], r['tasks']) == (12, 11, 30)
    assert sorted(r['gained']) == ['fastapi_11194', 'rich_3043'] and r['lost'] == ['rich_4077']
    assert r['p_mcnemar'] == 1.0


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('PASS', name)
