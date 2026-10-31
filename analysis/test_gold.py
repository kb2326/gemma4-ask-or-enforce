"""Checks for analysis/gold.py. Run: python analysis/test_gold.py"""

import json
from pathlib import Path

from gold import gold_locations, load_tasks_jsonl, oracle_hint

REPO = Path(__file__).resolve().parent.parent


def diff(*files, header='', added=''):
    out = []
    for f in files:
        out += [f'--- a/{f}', f'+++ b/{f}', f'@@ -10,6 +10,7 @@{header}', ' x = 1', f'+{added or "y = 2"}']
    return '\n'.join(out) + '\n'


def test_files_exclude_tests_and_docs():
    assert gold_locations(diff('rich/console.py', 'tests/test_console.py', 'docs/x.md'))['files'] == ['rich/console.py']


def test_functions_from_hunk_headers():
    patch = diff('rich/console.py', header=' def render(self, x):', added='def helper():')
    assert gold_locations(patch)['functions'] == ['render', 'helper']


def test_function_is_the_def_inside_the_hunk_not_the_header():
    """Review finding 3: the hunk header names the def *before* the hunk; a def shown inside the hunk wins."""
    patch = ('--- a/pkg/module.py\n+++ b/pkg/module.py\n'
             '@@ -900,7 +900,8 @@ def nested_helper(\n'
             ' \n'
             ' async def enclosing_function(\n'
             '     fields,\n'
             '-    x = 1\n'
             '+    x = 2\n')
    assert gold_locations(patch)['functions'] == ['enclosing_function']


def test_real_tasks_files_are_exact():
    """Known limit (review finding 3): when a hunk shows no def, its header names the nearest def before the hunk,
    which can be a nested helper rather than the function that changed. Resolving it needs the base-commit file, not
    available offline, so function names stay a heuristic and future ORACLE hints name files only.
    Files are always exact: checked on every practice task."""
    tasks = load_tasks_jsonl(REPO / 'data' / 'agent' / 'tasks.jsonl')
    for t in tasks.values():
        assert all(f.endswith('.py') and f'+++ b/{f}' in t['patch'] for f in gold_locations(t['patch'])['files'])


def test_files_only_hint():
    """Held-out ORACLE hints name files only (function names from hunk headers are a heuristic)."""
    assert oracle_hint({'files': ['a/b.py', 'c/d.py'], 'functions': ['f']}, files_only=True) == \
        'The fix belongs in: a/b.py, c/d.py.'


def test_test_only_patch_has_no_files():
    assert gold_locations(diff('tests/a.py'))['files'] == []


def test_hint_text():
    assert oracle_hint({'files': ['a/b.py'], 'functions': ['f']}) == \
        'The fix belongs in: a/b.py. Functions or classes involved: f.'
    assert oracle_hint({'files': ['a/b.py', 'c.py'], 'functions': []}) == 'The fix belongs in: a/b.py, c.py.'


def test_real_tasks():
    tasks = load_tasks_jsonl(REPO / 'data' / 'agent' / 'tasks.jsonl')
    counts = [len(gold_locations(tasks[i]['patch'])['files'])
              for i in json.loads((REPO / 'experiments' / 'practice30.json').read_text())]
    assert sorted(counts) == [1] * 24 + [2] * 6, counts


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
    print('all gold tests passed')
