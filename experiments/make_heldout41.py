"""Held-out set for the week of Oct 31 (amendment A9): heldout30.json plus the 11 trusted tasks never used.

Run: python experiments/make_heldout41.py   (writes experiments/heldout41.json, deterministic)
"""

import json
from pathlib import Path

HERE = Path(__file__).parent


def load(name):
    data = json.loads((HERE / name).read_text())
    return data['tasks'] if isinstance(data, dict) else data


if __name__ == '__main__':
    heldout, dev, trusted = load('heldout30.json'), load('practice30.json'), load('controls/trusted_tasks.json')
    unused = sorted(t for t in trusted if t not in heldout and t not in dev)
    tasks = heldout + unused
    assert len(tasks) == 41 and not set(tasks) & set(dev)
    (HERE / 'heldout41.json').write_text(json.dumps(tasks, indent=1) + '\n')
    print(f'wrote heldout41.json: {len(heldout)} held-out + {len(unused)} unused = {len(tasks)} tasks')
