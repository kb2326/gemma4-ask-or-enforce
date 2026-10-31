"""Check that the committed tree holds nothing the competition rules forbid us to publish (Rules section 4a).

Run:  python tools/check_public.py          (exit 1 and a list of problems if anything is found)
Needs the competition data in data/ (git-ignored) to know what to look for.

Not publishable: agent patches of practice tasks, anything derived from gold patches (ORACLE hints, gold file
columns), copies of the official sample submission, generated notebooks (they embed the sample files and hints),
and any text from task problem statements or gold patches.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SAMPLE = REPO / 'data' / 'agent' / 'sample_submission'
TASKS = REPO / 'data' / 'agent' / 'tasks.jsonl'


def tracked_files():
    out = subprocess.run(['git', 'ls-files'], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f]


def task_snippets():
    """Distinctive lines from each task's problem statement and gold patch."""
    snippets = {}
    for line in TASKS.read_text(encoding='utf-8').splitlines():
        t = json.loads(line)
        statement = [s.strip() for s in t['problem_statement'].splitlines() if len(s.strip()) > 60][:3]
        fix = [l[1:].strip() for l in t['patch'].splitlines()
               if l.startswith('+') and not l.startswith('+++') and len(l.strip()) > 45][:3]
        snippets[t['instance_id']] = statement + fix
    return snippets


def sample_chunks():
    """A distinctive chunk of every text file in the official sample submission."""
    return {p.relative_to(SAMPLE).as_posix(): p.read_text(encoding='utf-8').strip()[:160]
            for p in SAMPLE.rglob('*') if p.is_file() and p.suffix in ('.md', '.yaml', '.json')}


def problems(files):
    found = []
    snippets, chunks = task_snippets(), sample_chunks()
    for f in files:
        if '/patches/' in f or f.endswith('.patch'):
            found.append(f'{f}: agent patch of a practice task')
            continue
        if f.endswith('.ipynb'):
            found.append(f'{f}: generated notebook (embeds sample files and hints)')
            continue
        if f.endswith('hints.json'):
            found.append(f'{f}: derived from gold patches')
            continue
        try:
            text = (REPO / f).read_text(encoding='utf-8')
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for name, chunk in chunks.items():
            if len(chunk) > 40 and chunk in text:
                found.append(f'{f}: contains the official sample file {name}')
        for task, lines in snippets.items():
            if any(x in text for x in lines):
                found.append(f'{f}: contains text from task {task}')
                break
        if f.endswith('.csv') and 'gold_files,' in text.splitlines()[0] + ',':
            found.append(f'{f}: has a gold_files column')
    return found


def main():
    found = problems(tracked_files())
    for p in found:
        print('NOT PUBLIC-CLEAN:', p)
    print(f'{len(found)} problem(s)' if found else 'public-clean: no competition data in the committed tree')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
