"""Checks for analysis/paper_tables.py. Run: python analysis/test_paper_tables.py"""

from paper_tables import arm_row, dev_rows, fill_draft, heldout_rows


def stat(solved=False, first='', tmp='', overlap='', finder=''):
    return {'solved': str(solved), 'first_write_kind': first, 'first_write_in_tmp': tmp, 'patch_overlap': overlap,
            'finder_seconds': finder or '0', 'finder_runs': '1' if finder else '0'}


def test_arm_row_counts():
    results = [{'error': 'Agent exceeded session timeout (4.5 min)'}, {'error': ''}, {'error': ''}]
    stats = [stat(True, 'source', overlap='all'), stat(False, 'scratch', 'True', 'empty', '10'),
             stat(False, '', '', 'none', '20')]
    r = arm_row(results, stats)
    assert (r['solved'], r['tasks'], r['timeouts']) == (1, 3, 1)
    assert (r['source_first'], r['writers'], r['scratch_tmp'], r['scratch']) == (1, 2, 1, 1)
    assert r['no_source_edit'] == 1 and r['wrong_files_only'] == 1
    assert r['localizer_median_s'] == 15.0


def test_real_tables_match_logged_numbers():
    """Numbers already written in the results log must come out of the CSVs unchanged."""
    dev = {name: rows for name, rows in dev_rows()}
    assert [r['solved'] for r in dev['Reference']] == [11, 12, 13]
    assert sum(r['source_first'] for r in dev['Reference']) == 18 and sum(r['writers'] for r in dev['Reference']) == 70
    assert sum(r['source_first'] for r in dev['E5b']) == 24 and sum(r['writers'] for r in dev['E5b']) == 44
    held = dict(heldout_rows())
    assert [held[a]['solved'] for a in ('E2', 'E3.1', 'E5b', 'ORACLE')] == [14, 13, 10, 12]
    assert (held['E5b']['source_first'], held['E2']['source_first']) == (11, 10)
    assert (held['E3.1']['scratch_tmp'], held['E3.1']['scratch']) == (20, 20)
    assert held['E2']['localizer_median_s'] is None and held['E5b']['localizer_median_s'] == 13.8


def test_fill_draft_replaces_only_marked_blocks():
    tables = '# T\n\n## Table 1. One\n\n| a |\n\n## Table 2. Two\n\n| b |\n'
    draft = 'x\n<!-- TABLE 1 -->\nold\n<!-- /TABLE 1 -->\ny\n<!-- TABLE 2 -->\n<!-- /TABLE 2 -->\n'
    out = fill_draft(draft, tables)
    assert out == ('x\n<!-- TABLE 1 -->\n**Table 1. One**\n\n| a |\n<!-- /TABLE 1 -->\ny\n'
                   '<!-- TABLE 2 -->\n**Table 2. Two**\n\n| b |\n<!-- /TABLE 2 -->\n')
    assert fill_draft(out, tables) == out                  # rerunning changes nothing


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('PASS', name)
