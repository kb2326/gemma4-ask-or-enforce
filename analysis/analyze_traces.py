"""Measure every agent transcript of a run: where the time goes, which tools, what goes wrong.

Usage:  python analysis/analyze_traces.py data/runs/gemma4-practice30/results
Prints a per-task table and solved-vs-unsolved averages, and writes trace_stats.csv next to the results.
"""

import csv
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

from gold import gold_locations, load_tasks_jsonl

REPO = Path(__file__).resolve().parent.parent
EDIT_TOOLS = {'edit_file', 'write_file'}
GRAPH_TOOLS = {'get_code_neighbors', 'search_similar_code', 'get_code_subgraph'}
# Shell writes: `> file`, `>> file` after whitespace or at the start (not fd redirects like 2>&1, not `->` or `>=`),
# and `tee [-a] file`. Quoted strings and heredoc bodies are removed first, so code inside them is not read as shell.
REDIRECT = re.compile(r'(?:^|\s)>>?(?!=)\s*([^\s|;&<>=]+)')
TEE = re.compile(r'\btee\s+(?:-a\s+)?([^\s|;&<>]+)')
QUOTED = re.compile(r'"[^"]*"|\'[^\']*\'')


def is_source_path(path):
    """A file of the project's own code: inside a package folder, not a test, not a scratch or reproduction script.

    Scratch: anything under /tmp or another absolute path, new files at the repo root (repro.py, reproduce_issue.py),
    test files and folders, and repro*/reproduce* scripts wherever they are.
    """
    p = str(path).strip().strip('`"\'').removeprefix('/workspace/').removeprefix('./')
    if not p or p.startswith('/'):
        return False
    parts = p.split('/')
    base = parts[-1]
    return (len(parts) > 1 and parts[0] not in ('tests', 'test', 'docs') and '/tests/' not in f'/{p}'
            and not base.startswith(('test_', 'repro', 'reproduce')) and not base.endswith('_test.py'))


def shell_text(command):
    """The command with quoted strings and heredoc bodies removed."""
    lines = command.split('\n')
    head = next((i for i, l in enumerate(lines) if '<<' in l), None)
    if head is not None:
        lines = lines[:head + 1]
    return QUOTED.sub('""', '\n'.join(lines))


def write_targets(call):
    """Files a tool call writes, in order. Calls without a path are not writes."""
    args = call.get('arguments') or {}
    if call['function_name'] in EDIT_TOOLS:
        path = str(args.get('filepath', '')).strip()
        return [path] if path else []
    if call['function_name'] == 'run_command':
        command = shell_text(str(args.get('command', '')))
        return [t for t in REDIRECT.findall(command) + TEE.findall(command) if t and t != '/dev/null']
    return []


def names_file(text, path):
    """True if text names path as a path (also under /workspace) or as a dotted module; a bare basename does not count."""
    return path in text or path.removesuffix('.py').replace('/', '.') in text


def patch_overlap(patch_path, gold):
    if gold is None or not gold['files'] or not patch_path.exists():
        return ''
    edited = {f for f in re.findall(r'^\+\+\+ b/(\S+)', patch_path.read_text(encoding='utf-8'), re.M)
              if is_source_path(f)}
    if not edited:
        return 'empty'
    if set(gold['files']) <= edited:
        return 'all'
    return 'some' if set(gold['files']) & edited else 'none'


def stages(agent, finder):
    """Time and calls of the finder stage. A nudge restarts the pipeline, so the finder can run more than once."""
    runs, seconds, calls, prev_t, in_run, start, end = 0, 0.0, 0, 0.0, False, 0.0, 0.0
    for s in agent:
        t = s['extra']['elapsed_s']
        if s['extra'].get('author') == finder:
            if not in_run:
                runs, in_run, start = runs + 1, True, prev_t
            calls += len(s.get('tool_calls') or [])
            end = t
        elif in_run:
            seconds, in_run = seconds + end - start, False
        prev_t = t
    if in_run:
        seconds += end - start
    return runs, round(seconds, 1), calls


def failure_split(rows):
    """Where unsolved tasks went wrong, judged by which files the final patch touched."""
    split = {'no_source_edit': 0, 'wrong_files': 0, 'right_files': 0}
    for r in rows:
        if r['solved']:
            continue
        o = r['patch_overlap']
        if o == 'empty':
            split['no_source_edit'] += 1
        elif o == 'all':
            split['right_files'] += 1
        elif o == 'none':
            split['wrong_files'] += 1
        elif o == 'some':
            split['right_files'] += 0.5
            split['wrong_files'] += 0.5
    return split


def analyze(trace_path, resolved, gold=None, finder='localizer'):
    steps = json.loads(trace_path.read_text(encoding='utf-8'))['steps']
    agent = [s for s in steps if s.get('source') == 'agent']
    times = [s['extra']['elapsed_s'] for s in agent]
    calls = [c for s in agent for c in (s.get('tool_calls') or [])]
    names = Counter(c['function_name'] for c in calls)
    keys = Counter(json.dumps([c['function_name'], c.get('arguments')], sort_keys=True) for c in calls)
    obs = [json.dumps(s.get('observation') or '') for s in agent]
    prompt = [(s.get('metrics') or {}).get('prompt_tokens', 0) for s in agent]
    completion = [(s.get('metrics') or {}).get('completion_tokens', 0) for s in agent]
    thinking_chars = [len(s['message']) if isinstance(s.get('message'), str) else 0 for s in agent]

    def first_time(pred):
        return next((c['extra']['elapsed_s'] for c in calls if pred(c)), None)

    def is_source_edit(c):
        """An edit to the project's own code; scratch scripts, tests and /tmp files do not count."""
        return c['function_name'] in EDIT_TOOLS and is_source_path((c.get('arguments') or {}).get('filepath', ''))

    commands = [c['arguments'].get('command', '') for c in calls if c['function_name'] == 'run_command']
    writes = [w for c in calls for w in write_targets(c)]
    finder_runs, finder_seconds, finder_calls = stages(agent, finder)
    finder_steps = [s for s in agent if s['extra'].get('author') == finder]
    finder_text = next((s.get('message') or '' for s in reversed(finder_steps) if not s.get('tool_calls')), '')
    # elapsed_s marks the end of a step, so the fixer starts when the step before its first step ended.
    first_fixer = next((i for i, s in enumerate(agent) if s['extra'].get('author') != finder), None)
    fixer_start = (agent[first_fixer - 1]['extra']['elapsed_s'] if first_fixer else 0.0) if first_fixer is not None else None
    first_edit = first_time(is_source_edit)
    task = trace_path.stem.removeprefix('trace_')
    overlap = patch_overlap(trace_path.parent.parent / 'patches' / f'{task}.patch', gold)
    has_finder = bool(finder_steps)
    known_prompt = [x for x in prompt if x > 0]
    return {
        'task': trace_path.stem.removeprefix('trace_'),
        'solved': resolved,
        'steps': len(agent),
        # Agent-only time: the trace's last timestamp. Total time in results.csv also includes setup and grading.
        'seconds': round(times[-1], 1) if times else 0,
        'sec_per_step': round(times[-1] / len(times), 1) if times else 0,
        'tool_calls': len(calls),
        'reads': names['read_file'],
        'edits': sum(is_source_edit(c) for c in calls),
        'scratch_writes': sum(c['function_name'] in EDIT_TOOLS and bool(write_targets(c)) and not is_source_edit(c)
                              for c in calls),
        'commands': names['run_command'],
        'test_runs': sum('pytest' in cmd or 'unittest' in cmd for cmd in commands),
        'graph_calls': sum(names[t] for t in GRAPH_TOOLS),
        'analyzer_calls': sum(n for t, n in names.items() if 'analyzer' in t),
        'repeated_calls': sum(n - 1 for n in keys.values() if n > 1),
        'tool_errors': sum('\\"status\\": \\"error\\"' in o for o in obs),
        'first_edit_s': first_time(is_source_edit),
        # Same, but tasks that never edited count as editing at the very end, so averages cover every task.
        'first_edit_or_end_s': first_time(is_source_edit) or (round(times[-1], 1) if times else 0),
        'submitted': names['submit_patch'] > 0,
        'peak_context_tokens': max(prompt, default=0),
        'output_tokens_per_step': round(statistics.mean(completion), 0) if completion else 0,
        'thinking_chars_per_step': round(statistics.mean(thinking_chars), 0) if thinking_chars else 0,
        # ADK compaction replaces old events with a summary, so the prompt suddenly shrinks.
        # Steps without metrics (final replies) report 0 prompt tokens; those are missing data, not a shrunk prompt.
        'compacted': any(p < 0.7 * max(known_prompt[:i]) for i, p in enumerate(known_prompt) if i),
        'first_write_kind': ('source' if is_source_path(writes[0]) else 'scratch') if writes else '',
        # For scratch-first tasks: was the script put under /tmp (the E3.1 prompt asks for that)?
        'first_write_in_tmp': (str(writes[0]).strip().startswith('/tmp')
                               if writes and not is_source_path(writes[0]) else ''),
        'finder_runs': finder_runs,
        'finder_seconds': finder_seconds,
        'finder_tool_calls': finder_calls,
        'fixer_seconds': round(times[-1] - finder_seconds, 1) if (times and finder_runs) else 0,
        'first_edit_from_fixer_s': (round(first_edit - fixer_start, 1)
                                    if finder_runs and first_edit is not None and fixer_start is not None else ''),
        'nudges': sum(s.get('source') == 'system' and (s.get('extra') or {}).get('event_type') == 'continuation_nudge'
                      for s in steps),
        'patch_overlap': overlap,
        'gold_files_edited': (overlap == 'all') if overlap else '',
        'finder_files_hit': (all(names_file(finder_text, f) for f in gold['files'])
                             if has_finder and gold and gold['files'] else ''),
        'finder_functions_hit': (all(n in finder_text for n in gold['functions'])
                                 if has_finder and gold and gold['functions'] else ''),
    }


def main(results_dir, tasks_jsonl=REPO / 'data' / 'agent' / 'tasks.jsonl'):
    results_dir = Path(results_dir)
    tasks = load_tasks_jsonl(tasks_jsonl) if Path(tasks_jsonl).exists() else {}
    outcome = {}
    for line in (results_dir / 'baseline.jsonl').read_text(encoding='utf-8').splitlines():
        if line.strip():
            r = json.loads(line)
            outcome[r['instance_id']] = r['agent_resolved']
    rows = []
    for p in sorted((results_dir / 'traces').glob('trace_*.json')):
        task = p.stem.removeprefix('trace_')
        gold = gold_locations(tasks[task]['patch']) if task in tasks else None
        rows.append(analyze(p, outcome.get(task), gold=gold))

    cols = ['task', 'solved', 'seconds', 'steps', 'sec_per_step', 'reads', 'edits', 'test_runs', 'graph_calls',
            'analyzer_calls', 'repeated_calls', 'tool_errors', 'first_edit_s', 'submitted', 'peak_context_tokens']
    print(' '.join(f'{c[:12]:>12}' for c in cols))
    for r in sorted(rows, key=lambda r: (not r['solved'], r['seconds'])):
        print(' '.join(f'{str(r[c])[:12]:>12}' for c in cols))

    numeric = [k for k, v in rows[0].items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    print('\nAverages          solved  unsolved')
    for k in numeric:
        groups = [[r[k] for r in rows if r['solved'] == s and isinstance(r[k], (int, float)) and not isinstance(r[k], bool)]
                  for s in (True, False)]
        print(f'{k:<26}' + ''.join(f'{statistics.mean(g):>9.1f}' if g else f'{"-":>9}' for g in groups))
    print('\nCounts            solved  unsolved')
    for k in ('submitted', 'compacted'):
        print(f'{k:<26}' + ''.join(f'{sum(r[k] for r in rows if r["solved"] == s):>9}' for s in (True, False)))
    print(f'{"never edited":<26}' + ''.join(f'{sum(r["edits"] == 0 for r in rows if r["solved"] == s):>9}' for s in (True, False)))

    split = failure_split(rows)
    print(f"failure split (unsolved): no source edit {split['no_source_edit']:g} | wrong files {split['wrong_files']:g} | "
          f"right files {split['right_files']:g}")
    kinds = Counter(r['first_write_kind'] for r in rows)
    print(f"first write: source {kinds['source']} | scratch {kinds['scratch']} | none {kinds['']}")

    with (results_dir / 'trace_stats.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'data/runs/gemma4-practice30/results')
