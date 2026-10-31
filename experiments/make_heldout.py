"""Freeze the held-out test set: 30 trustworthy tasks never used for tuning.

Procedure (recorded so it can be reproduced exactly):
  pool    = trusted tasks (experiments/controls/trusted_tasks.json) not in experiments/practice30.json
  split   = per repo, proportional to the pool (fastapi 16, rich 25 -> 12 and 18)
  sample  = random.Random(SEED).sample(sorted(pool_for_repo), k)
Run: python experiments/make_heldout.py  ->  writes experiments/heldout30.json
"""

import json
import random
from pathlib import Path

SEED = 20261019
SIZE = 30
HERE = Path(__file__).parent

trusted = json.loads((HERE / 'controls' / 'trusted_tasks.json').read_text())
practice = set(json.loads((HERE / 'practice30.json').read_text()))
pool = sorted(t for t in trusted if t not in practice)

by_repo = {}
for t in pool:
    by_repo.setdefault(t.split('_')[0], []).append(t)

rng = random.Random(SEED)
picked = []
repos = sorted(by_repo)
quota = {r: round(SIZE * len(by_repo[r]) / len(pool)) for r in repos}
quota[repos[-1]] = SIZE - sum(quota[r] for r in repos[:-1])
for r in repos:
    picked += rng.sample(by_repo[r], quota[r])

assert len(picked) == SIZE and not set(picked) & practice
(HERE / 'heldout30.json').write_text(json.dumps(sorted(picked), indent=1) + '\n')
print(f'pool {len(pool)} ({ {r: len(v) for r, v in by_repo.items()} }) -> picked {quota}, seed {SEED}')
