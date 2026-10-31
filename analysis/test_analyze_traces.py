"""Checks for the new measurements in analysis/analyze_traces.py. Run: python analysis/test_analyze_traces.py"""

import json
import tempfile
from pathlib import Path

from analyze_traces import analyze, failure_split

GOLD = {'files': ['rich/console.py'], 'functions': ['render']}


def step(author, t, calls=(), text=None, tokens=1000):
    return {'source': 'agent', 'message': text or 'thinking...',
            'tool_calls': [{'function_name': n, 'arguments': a, 'extra': {'elapsed_s': t}} for n, a in calls],
            'metrics': {'prompt_tokens': tokens}, 'extra': {'author': author, 'elapsed_s': t}}


NUDGE = {'source': 'system', 'message': 'Please continue', 'extra': {'event_type': 'continuation_nudge', 'elapsed_s': 0}}


def run(steps, gold=GOLD, patch=None):
    d = Path(tempfile.mkdtemp())
    (d / 'traces').mkdir()
    (d / 'patches').mkdir()
    p = d / 'traces' / 'trace_t1.json'
    p.write_text(json.dumps({'steps': steps}))
    if patch is not None:
        (d / 'patches' / 't1.patch').write_text(patch)
    return analyze(p, False, gold=gold)


def cmd(c):
    return ('run_command', {'command': c})


def test_first_write_kinds():
    assert run([step('a', 1, [cmd('cat > rich/x.py <<END\nx\nEND')])])['first_write_kind'] == 'source'
    assert run([step('a', 1, [cmd('echo 1 > /tmp/t.py')]),
                step('a', 2, [('edit_file', {'filepath': 'rich/console.py'})])])['first_write_kind'] == 'scratch'
    assert run([step('a', 1, [cmd('pytest 2>&1 | tail'), cmd('ls > /dev/null')])])['first_write_kind'] == ''
    assert run([step('a', 1, [('write_file', {'filepath': '/tmp/r.py'})])])['first_write_kind'] == 'scratch'


def test_stage_split_and_restart():
    r = run([step('localizer', 10, [('read_file', {})]), step('localizer', 20, text='rich/console.py: render'),
             step('fixer', 30, [('edit_file', {'filepath': 'rich/console.py'})]), step('fixer', 40, text='done'), NUDGE,
             step('localizer', 50, [('read_file', {})]), step('localizer', 60, text='rich/console.py'),
             step('fixer', 70, [('submit_patch', {})])])
    assert r['finder_runs'] == 2 and r['nudges'] == 1
    assert r['finder_tool_calls'] == 2
    assert r['finder_seconds'] == 40            # pass 1: 0 -> 20 s; pass 2: 40 -> 60 s
    assert r['first_edit_from_fixer_s'] == 10   # fixer starts when the localizer's step ends (20 s); edit at 30 s


def test_finder_never_finishes():
    r = run([step('localizer', 10, [('read_file', {})]), step('localizer', 270, [('read_file', {})])])
    assert r['finder_files_hit'] is False and r['first_write_kind'] == ''


def test_path_spellings():
    for text, hit in [('see /workspace/rich/console.py', True), ('in rich.console, render', True),
                      ('rich/console.py', True), ('console.py', False)]:
        r = run([step('localizer', 5, text=text)])
        assert r['finder_files_hit'] is hit, text


def test_functions_hit():
    assert run([step('localizer', 5, text='rich/console.py: render()')])['finder_functions_hit'] is True
    assert run([step('localizer', 5, text='rich/console.py')])['finder_functions_hit'] is False


def test_no_gold_files():
    r = run([step('localizer', 5, text='x')], gold={'files': [], 'functions': []}, patch='')
    assert r['finder_files_hit'] == '' and r['gold_files_edited'] == '' and r['finder_functions_hit'] == ''


def test_single_agent_has_no_stages():
    r = run([step('swe_baseline_agent', 5, [('read_file', {})])])
    assert r['finder_runs'] == 0 and r['finder_seconds'] == 0 and r['first_edit_from_fixer_s'] == ''


def test_compaction_detected():
    def toks(*ts):
        return [step('a', i, tokens=t) for i, t in enumerate(ts)]
    assert run(toks(3000, 9000, 15000, 4000))['compacted'] is True
    assert run(toks(3000, 9000, 15000))['compacted'] is False


def test_patch_overlap_and_failure_split():
    def p(*fs):
        return ''.join(f'--- a/{f}\n+++ b/{f}\n@@ -1 +1 @@\n-a\n+b\n' for f in fs)
    two = {'files': ['pkg/a.py', 'pkg/b.py'], 'functions': []}
    assert run([step('a', 1)], patch=p('rich/console.py'))['patch_overlap'] == 'all'
    assert run([step('a', 1)], patch=p('rich/other.py'))['patch_overlap'] == 'none'
    assert run([step('a', 1)], patch='')['patch_overlap'] == 'empty'
    assert run([step('a', 1)], gold=two, patch=p('pkg/a.py'))['patch_overlap'] == 'some'
    rows = [{'solved': False, 'patch_overlap': o} for o in ('empty', 'none', 'all', 'some')] + \
           [{'solved': True, 'patch_overlap': 'all'}]
    assert failure_split(rows) == {'no_source_edit': 1, 'wrong_files': 1.5, 'right_files': 1.5}


def test_main_averages_skip_blank_values():
    """first_edit_from_fixer_s is a number on some tasks and '' on others (E5 run); averages must skip the blanks."""
    from analyze_traces import main
    d = Path(tempfile.mkdtemp())
    (d / 'traces').mkdir()
    edit = [step('localizer', 5, text='x'), step('fixer', 9, [('edit_file', {'filepath': 'a.py'})])]
    no_edit = [step('localizer', 5, text='x'), step('fixer', 9, [('read_file', {})])]
    for name, steps in (('t1', edit), ('t2', no_edit)):
        (d / 'traces' / f'trace_{name}.json').write_text(json.dumps({'steps': steps}))
    (d / 'baseline.jsonl').write_text('{"instance_id": "t1", "agent_resolved": true}\n'
                                      '{"instance_id": "t2", "agent_resolved": false}\n')
    main(d, tasks_jsonl=d / 'missing.jsonl')
    assert (d / 'trace_stats.csv').exists()


def test_repo_root_scripts_and_tests_are_scratch():
    """Review finding 1: E2 writes reproduce_issue.py at the repo root first; that is a scratch script, not source."""
    for path, kind in [('reproduce_issue.py', 'scratch'), ('/workspace/repro.py', 'scratch'),
                       ('tests/test_x.py', 'scratch'), ('/tmp/r.py', 'scratch'),
                       ('rich/console.py', 'source'), ('/workspace/fastapi/routing.py', 'source'),
                       ('`fastapi/routing.py`', 'source')]:
        assert run([step('a', 1, [('write_file', {'filepath': path})])])['first_write_kind'] == kind, path


def test_redirect_false_positives_and_empty_paths():
    """Review finding 5: '->' and '>=' are not redirects; a write_file without a path is not a write."""
    for c in ['grep -n "def f() -> None:" a.py', 'python3 -c "print(1 >= 0)"', 'python3 -c "x = a > b"']:
        assert run([step('a', 1, [cmd(c)])])['first_write_kind'] == '', c
    assert run([step('a', 1, [('write_file', {})]),
                step('a', 2, [('edit_file', {'filepath': 'rich/console.py'})])])['first_write_kind'] == 'source'


def test_edits_and_patch_ignore_scratch_files():
    """Review finding 2: a patch that only adds repro.py is 'no source edit', not 'wrong files'."""
    r = run([step('a', 1, [('write_file', {'filepath': 'repro.py'})])],
            patch='--- /dev/null\n+++ b/repro.py\n@@ -0,0 +1 @@\n+x\n')
    assert r['edits'] == 0 and r['patch_overlap'] == 'empty'


def test_fixer_clock_starts_when_localizer_ends():
    """Review finding 4: elapsed_s marks the end of a step, so the fixer starts at the localizer's last step."""
    r = run([step('localizer', 20, text='rich/console.py'), step('fixer', 30, [('edit_file', {'filepath': 'rich/console.py'})])])
    assert r['first_edit_from_fixer_s'] == 10


def test_first_write_location_for_scratch():
    """C1 (held-out): where a scratch-first task put its script: under /tmp or not ('' when the first write is source)."""
    assert run([step('a', 1, [('write_file', {'filepath': '/tmp/repro.py'})])])['first_write_in_tmp'] is True
    assert run([step('a', 1, [('write_file', {'filepath': 'reproduce_issue.py'})])])['first_write_in_tmp'] is False
    assert run([step('a', 1, [('edit_file', {'filepath': 'rich/console.py'})])])['first_write_in_tmp'] == ''
    assert run([step('a', 1, [('read_file', {})])])['first_write_in_tmp'] == ''


def test_steps_without_metrics_are_not_compaction():
    """Review finding 6: final steps carry no prompt_tokens; a 0 is missing data, not a shrunk prompt."""
    assert run([step('a', 0, tokens=3000), step('a', 1, tokens=9000), step('a', 2, tokens=0)])['compacted'] is False


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
    print('all analyze_traces tests passed')
