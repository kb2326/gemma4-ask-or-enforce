"""Print one agent transcript step by step: time, thinking, tool call, short result.

Usage:  python analysis/show_trace.py data/runs/gemma4-practice30/results rich_3180 [chars]
"""

import json
import sys
from pathlib import Path


def main(results_dir, task, width=400):
    steps = json.loads((Path(results_dir) / 'traces' / f'trace_{task}.json').read_text(encoding='utf-8'))['steps']
    prompt = next((s['message'] for s in steps if s.get('source') == 'user'), '')
    print('ISSUE:', prompt.split('Problem Statement:')[-1].split('##')[0].strip()[:width], '\n')
    prev = 0.0
    for s in steps:
        if s.get('source') != 'agent':
            continue
        t = s['extra']['elapsed_s']
        tokens = (s.get('metrics') or {}).get('completion_tokens', 0)
        think = (s.get('message') or '').replace('\n', ' ') if isinstance(s.get('message'), str) else ''
        print(f'[{t:6.1f}s  +{t - prev:5.1f}s  {tokens:>4} out-tokens]  {think[:width]}')
        for c in s.get('tool_calls') or []:
            args = json.dumps(c.get('arguments'), ensure_ascii=False)
            print(f'      -> {c["function_name"]}({args[:200]})')
        obs = s.get('observation')
        if obs:
            text = json.dumps(obs, ensure_ascii=False)
            print(f'      <- {text[:160]}')
        prev = t


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 400)
