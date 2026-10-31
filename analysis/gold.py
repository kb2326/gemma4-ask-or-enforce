"""Where the real fix is: source files and functions changed by a task's gold patch.

Usage:  python analysis/gold.py hints
Writes experiments/oracle/hints.json: one plain-text hint per practice task (files and function names only,
no code, no line numbers), used by the ORACLE run.
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HUNK_FUNC = re.compile(r'^@@ .*? @@\s*(?:async\s+)?(?:def|class)\s+(\w+)')
LINE_DEF = re.compile(r'^\s*(?:async\s+)?(?:def|class)\s+(\w+)')


def is_source(path):
    return (path.endswith('.py') and not path.startswith(('docs/', 'docs_src/', 'tests/', 'test/'))
            and '/tests/' not in path)


def gold_locations(patch):
    """Source files a patch changes, and the functions/classes its changed lines sit in.

    The hunk header names the nearest def *before* the hunk, so a def shown inside the hunk's context replaces it.
    """
    files, functions, current, func = [], [], None, None

    def add(name):
        if name and name not in functions:
            functions.append(name)

    for line in patch.splitlines():
        if line.startswith('+++ '):
            path = line[len('+++ b/'):].strip() if line.startswith('+++ b/') else ''
            current = path if is_source(path) else None
            if current and current not in files:
                files.append(current)
            continue
        if line.startswith('--- ') or current is None:
            continue
        if line.startswith('@@'):
            m = HUNK_FUNC.match(line)
            func = m.group(1) if m else None
        elif line.startswith(' '):
            m = LINE_DEF.match(line[1:])
            if m:
                func = m.group(1)
        elif line.startswith(('+', '-')):
            add(func)
            m = LINE_DEF.match(line[1:])
            if m:
                add(m.group(1))
    return {'files': files, 'functions': functions}


def oracle_hint(loc, files_only=False):
    hint = f"The fix belongs in: {', '.join(loc['files'])}."
    if loc['functions'] and not files_only:
        hint += f" Functions or classes involved: {', '.join(loc['functions'])}."
    return hint


def load_tasks_jsonl(path):
    rows = (json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip())
    return {r['instance_id']: r for r in rows}


def write_hints(task_set='practice30', files_only=False):
    """practice30 -> experiments/oracle/hints.json (files and functions, as used by ORACLE r1/r2);
    heldout41 -> experiments/oracle/hints_heldout41.json (files only, as pre-registered for the held-out week)."""
    tasks = load_tasks_jsonl(REPO / 'data' / 'agent' / 'tasks.jsonl')
    ids = json.loads((REPO / 'experiments' / f'{task_set}.json').read_text())
    hints = {i: oracle_hint(gold_locations(tasks[i]['patch']), files_only=files_only) for i in ids}
    name = 'hints.json' if task_set == 'practice30' else f'hints_{task_set}.json'
    out = REPO / 'experiments' / 'oracle' / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(hints, indent=1) + '\n', encoding='utf-8')
    print(f'wrote {len(hints)} hints to {out}')


if __name__ == '__main__':
    if sys.argv[1:] == ['hints']:
        write_hints()
    elif sys.argv[1:] == ['hints', 'heldout41']:
        write_hints('heldout41', files_only=True)
    else:
        print(__doc__)
