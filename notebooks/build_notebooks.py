"""Build the Kaggle practice notebooks from shared cells.

Run:  python notebooks/build_notebooks.py             (the standard notebooks)
      python notebooks/build_notebooks.py --arm oracle  (one experiment arm, see ARMS)
Writes notebooks/controls/controls.ipynb and notebooks/baseline/baseline.ipynb.
Both are adapted from the official "Getting Started - Gemma 4 Developer Agent" notebook.
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

BASELINE_TASK_IDS = ['fastapi_14786', 'rich_3043', 'rich_4077', 'rich_3882', 'fastapi_14479']

REPO = HERE.parent
PRACTICE30 = json.loads((REPO / 'experiments' / 'practice30.json').read_text())


SAMPLE = REPO / 'data' / 'agent' / 'sample_submission'      # official sample, from the competition data (not in git)
OFFICIAL_PROMPT_MARKER = '<<OFFICIAL SAMPLE PROMPT>>'          # replaced by the sample's prompts/system.md


def text_files(root):
    return {p.relative_to(root).as_posix(): p.read_text(encoding='utf-8')
            for p in sorted(Path(root).rglob('*'))
            if p.is_file() and p.suffix in ('.yaml', '.yml', '.md', '.txt', '.json')}


def submission_files(root, overrides=None):
    """Text files of an agent folder, embedded into notebooks at build time.

    Practice runs and the real submission both use these, so what we test is what we submit.
    The repo stores only our own files (the competition's sample may not be redistributed): a folder without
    agent.yaml (the repo's submission/) is laid over the official sample, and the marker line in a prompt is replaced
    by the official sample prompt. `overrides` swaps single files, e.g. {'prompts/system.md': <another prompt>}.
    """
    files = {} if (Path(root) / 'agent.yaml').exists() else text_files(SAMPLE)
    files.update(text_files(root))
    for rel, src in (overrides or {}).items():
        files[rel] = Path(src).read_text(encoding='utf-8')
    official = (SAMPLE / 'prompts' / 'system.md').read_text(encoding='utf-8')
    return {rel: text.replace(OFFICIAL_PROMPT_MARKER, official) for rel, text in files.items()}


def md(text):
    return {'cell_type': 'markdown', 'metadata': {}, 'source': text.strip('\n')}


def code(text):
    return {'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': text.strip('\n')}


# ---------------------------------------------------------------------------
# Shared cells
# ---------------------------------------------------------------------------

SETUP = code(r'''
import glob
import importlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Offline vLLM serving and quiet LiteLLM (same settings as the official notebook)
os.environ['TRANSFORMERS_NO_TF'] = '1'
os.environ['TRANSFORMERS_NO_FLAX'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['VLLM_NO_USAGE_STATS'] = '1'
os.environ['VLLM_WORKER_MULTIPROC_METHOD'] = 'spawn'
os.environ['VLLM_ENGINE_READY_TIMEOUT_S'] = '1200'
os.environ['VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS'] = '1'
os.environ['NCCL_DEBUG'] = 'WARN'
os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
os.environ['LITELLM_TELEMETRY'] = 'False'
os.environ['LITELLM_LOG'] = 'WARNING'
os.environ['OPENAI_API_KEY'] = os.environ.get('OPENAI_API_KEY', 'EMPTY')
os.environ['LOCAL_API_KEY'] = os.environ.get('LOCAL_API_KEY', 'EMPTY')
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
os.environ['OTEL_SDK_DISABLED'] = 'true'
os.environ['OTEL_PYTHON_DISABLED'] = 'true'


def configure_logging():
    for name in ('LiteLLM', 'LiteLLM Router', 'LiteLLM Proxy', 'litellm', 'httpx',
                 'httpcore', 'openai', 'urllib3', 'opentelemetry', 'opentelemetry.context'):
        lg = logging.getLogger(name)
        lg.setLevel(logging.WARNING)
        if 'litellm' in name.lower():
            lg.propagate = False
            lg.handlers.clear()


def find_input(*candidates):
    """Kaggle mounts inputs at slightly different paths depending on the image."""
    for c in candidates:
        if Path(c).exists():
            return Path(c)
    raise FileNotFoundError(f'None of these input paths exist: {candidates}')


configure_logging()
T_START = time.perf_counter()

# The wheelhouse is built for Python 3.12 (cp312). Fail fast on any other image.
assert sys.version_info[:2] == (3, 12), (
    f'Python {sys.version.split()[0]} found, but the wheelhouse needs 3.12. '
    'Pin the official Docker image in kernel-metadata.json.')

WHEELHOUSE_DIR = find_input('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse',
                            '/kaggle/input/gemma-4-developer-agent-wheelhouse')
DATA_DIR = find_input('/kaggle/input/competitions/gemma-4-developer-agent',
                      '/kaggle/input/gemma-4-developer-agent')
WORK = Path('/kaggle/working')
RESULTS = WORK / 'results'
RESULTS.mkdir(parents=True, exist_ok=True)

# Remove broken cutlass .pth hooks if present
for pattern in ('/usr/local/lib/python*/dist-packages/*cutlass*.pth',
                '/usr/local/lib/python*/site-packages/*cutlass*.pth'):
    for pth in glob.glob(pattern):
        try:
            os.unlink(pth)
        except OSError:
            pass

# Restore '+cu128' wheel filenames that Kaggle dataset uploads strip
tmp_whl = Path('/tmp/wheelhouse')
tmp_whl.mkdir(parents=True, exist_ok=True)
for w in WHEELHOUSE_DIR.glob('*.whl'):
    if 'cutlass' in w.name.lower():
        continue
    target_name = w.name.replace('cu128', '+cu128') if ('cu128' in w.name and '+' not in w.name) else w.name
    target = tmp_whl / target_name
    if not target.exists():
        try:
            os.symlink(w, target)
        except OSError:
            shutil.copyfile(w, target)

wheels = sorted(str(w) for w in tmp_whl.glob('*.whl'))

# Pin the harness: these three wheels must be byte-identical to the ones every earlier run used.
HARNESS_WHEEL_SHA256 = {
    'adk_eval_core-': 'e614e1b2fe8d886a634871e4c57f9887e1cc66e8c27300f8503a43c6e3ca82f3',
    'adk_submission-': 'f156f0bd84580ccb9334726d114d7a5481f16d3a6e2887cc4d276ced0ef8d99d',
    'swegemma-': '9ad876581f3acde8ec3c369858f0834e2b9f41a3cffce3ca42f09cb090aea9d3',
}
import hashlib
for w in map(Path, wheels):
    want = next((v for k, v in HARNESS_WHEEL_SHA256.items() if w.name.startswith(k)), None)
    if want:
        got = hashlib.sha256(w.read_bytes()).hexdigest()
        assert got == want, f'Wheelhouse changed: {w.name} sha256 {got}; expected {want}. Re-check the harness before running.'
HARNESS_SHA256_OK = True
print(f'Installing {len(wheels)} wheels from {WHEELHOUSE_DIR} ...')
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '--force-reinstall', *wheels], check=True)
importlib.invalidate_caches()
configure_logging()
print(f'Wheelhouse installed in {time.perf_counter() - T_START:.0f}s')
''')

def _git(*args):
    try:
        return subprocess.run(['git', *args], cwd=HERE, capture_output=True, text=True).stdout.strip()
    except OSError:
        return ''


BUILD_COMMIT = _git('rev-parse', 'HEAD')
BUILD_DIRTY = bool(_git('status', '--porcelain', '--', '../submission', '.'))

HARDWARE = code(r'''
# What machine did we actually get? Saved with the results so every run records its hardware and code version.
print('Python', sys.version.split()[0], '| CPU cores:', os.cpu_count())
smi = shutil.which('nvidia-smi')
gpus = subprocess.run([smi, '-L'], capture_output=True, text=True).stdout if smi else ''
print(gpus or 'No GPU (CPU-only session)')
(RESULTS / 'run_info.json').write_text(json.dumps({
    'built_from_commit': ''' + repr(BUILD_COMMIT) + r''',
    'uncommitted_changes_at_build': ''' + repr(BUILD_DIRTY) + r''',
    'python': sys.version.split()[0], 'cpu_cores': os.cpu_count(),
    'gpus': [g for g in gpus.splitlines() if g.strip()],
    'wheels': [{'name': Path(w).name, 'bytes': Path(w).stat().st_size} for w in wheels],
    'harness_sha256_ok': HARNESS_SHA256_OK,
}, indent=1))
''')

RUN_SYNC = code(r'''
import asyncio
import concurrent.futures


def run_sync(coro_fn, *args, **kwargs):
    """Run an async function to completion from inside the notebook's own event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro_fn(*args, **kwargs))).result()
    return asyncio.run(coro_fn(*args, **kwargs))
''')

CONTROL_FN = code(r'''
from swegemma.deduplication import resolve_task_snapshot_paths
from swegemma.harness.verification import verify_task


async def grade_patch(evaluator, eval_config, task, patch):
    """Grade a patch exactly like the scorer's Phase 2, with no agent involved."""
    snapshot, base_snapshot, patch_path = resolve_task_snapshot_paths(
        eval_config.snapshots_dir, task.instance_id, task.repo)
    t0 = time.perf_counter()
    try:
        r = await verify_task(evaluator.docker, eval_config, task, snapshot,
                              base_snapshot_path=base_snapshot, patch_path=patch_path,
                              agent_patch=patch, start_time=t0)
        return {'resolved': bool(r.resolved), 'exit_code': r.test_exit_code,
                'error': (r.error or '')[:300], 'seconds': round(time.perf_counter() - t0, 1),
                'test_tail': (r.test_output or '')[-1500:]}
    except Exception as e:  # keep going: one broken task must not stop the run
        return {'resolved': False, 'exit_code': None, 'error': f'{type(e).__name__}: {e}'[:300],
                'seconds': round(time.perf_counter() - t0, 1), 'test_tail': ''}


def verdict(gold_pass, empty_pass):
    if not gold_pass:
        return 'broken_env'          # even the real fix fails: environment problem
    if empty_pass:
        return 'tests_blind'         # passes with no fix: tests don't detect the bug here
    return 'trustworthy'             # real fix passes, no fix fails: a fair task
''')


def agent_cell(files):
    """Rebuild the agent folder: the official sample (for the binary LoRA files), then our repo's text files on top."""
    return code(r'''
AGENT_FILES = ''' + repr(files) + r'''

AGENT_DIR = WORK / 'agent'
if AGENT_DIR.exists():
    shutil.rmtree(AGENT_DIR)
shutil.copytree(DATA_DIR / 'sample_submission', AGENT_DIR)   # provides adapters/*/adapter_model.safetensors
for child in list(AGENT_DIR.iterdir()):                      # keep only the sample's adapters; the rest is ours
    if child.name != 'adapters':
        shutil.rmtree(child) if child.is_dir() else child.unlink()
for rel, text in AGENT_FILES.items():                       # our repo's version of every text file
    (AGENT_DIR / rel).parent.mkdir(parents=True, exist_ok=True)
    (AGENT_DIR / rel).write_text(text, encoding='utf-8')
print((AGENT_DIR / 'agent.yaml').read_text())
print((AGENT_DIR / 'eval_config.yaml').read_text())
''')

# ---------------------------------------------------------------------------
# Controls notebook (CPU only)
# ---------------------------------------------------------------------------

controls = [
    md('''
# Task controls: which practice tasks can we trust?

**Why this notebook exists.** Before measuring the agent, we test the test. For every practice task we grade:

1. the **gold patch** (the developer's real fix). It *must pass*. If it fails, the notebook environment is broken for that task.
2. an **empty patch** (no change). It *must fail*. If it passes, the tests don't detect the bug here (for example they test the installed library instead of the workspace code).

Only tasks where gold passes and empty fails are **trustworthy** for measuring our agent.
This runs on CPU only and uses **no GPU quota**. Grading uses the harness's own `verify_task`, the same code as the scorer's Phase 2.
'''),
    md('## 1. Install the harness from the wheelhouse (offline)'),
    SETUP,
    HARDWARE,
    md('## 2. Configure a grader with no model'),
    code(r'''
from adk_submission import ModelRegistry
from swegemma.config import EvalConfig
from swegemma.evaluate import Evaluator
from swegemma.models import load_tasks

tasks = load_tasks(DATA_DIR / 'tasks.jsonl')
eval_config = EvalConfig(
    tasks_path=DATA_DIR / 'tasks.jsonl',
    snapshots_dir=DATA_DIR / 'snapshots',
    results_dir=RESULTS,
    submission_dir=WORK,
    models=ModelRegistry(),          # empty: no model is needed to grade a patch
    sandbox='subprocess',            # Docker is not available in Kaggle notebooks
    wheels_dir=DATA_DIR / 'wheels',
    graph_dir=str(DATA_DIR / 'graphs'),
    embeddings_dir=str(DATA_DIR / 'embeddings'),
    verification_timeout_seconds=300,
)
evaluator = Evaluator(eval_config)
CONCURRENCY = max(1, min(4, os.cpu_count() or 1))
print(f'{len(tasks)} tasks, grading {CONCURRENCY} at a time')
'''),
    RUN_SYNC,
    CONTROL_FN,
    md('## 3. Grade gold and empty patches for every task\nResults are written after every task, so a crash still leaves partial results.'),
    code(r'''
import pandas as pd

OUT = RESULTS / 'controls.jsonl'
done = set()
if OUT.exists():
    done = {json.loads(l)['instance_id'] for l in OUT.read_text().splitlines() if l.strip()}


async def control_all():
    sem = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()

    async def one(task):
        async with sem:
            gold = await grade_patch(evaluator, eval_config, task, task.patch)
            empty = await grade_patch(evaluator, eval_config, task, '')
        row = {'instance_id': task.instance_id, 'repo': task.repo,
               'verdict': verdict(gold['resolved'], empty['resolved']),
               **{f'gold_{k}': v for k, v in gold.items()},
               **{f'empty_{k}': v for k, v in empty.items()}}
        async with lock:
            with OUT.open('a') as f:
                f.write(json.dumps(row) + '\n')
            print(f"{row['instance_id']:<16} {row['verdict']:<12} gold={gold['seconds']}s empty={empty['seconds']}s {gold['error'][:80]}")

    await asyncio.gather(*(one(t) for t in tasks if t.instance_id not in done))

run_sync(control_all)
'''),
    md('## 4. Summary'),
    code(r'''
df = pd.DataFrame([json.loads(l) for l in OUT.read_text().splitlines() if l.strip()])
df.drop(columns=[c for c in df.columns if c.endswith('test_tail')]).to_csv(RESULTS / 'controls.csv', index=False)
print(pd.crosstab(df['repo'], df['verdict'], margins=True))
trusted = sorted(df.loc[df['verdict'] == 'trustworthy', 'instance_id'])
(RESULTS / 'trusted_tasks.json').write_text(json.dumps(trusted, indent=1))
print(f'\n{len(trusted)} trustworthy tasks saved to trusted_tasks.json')
print(f'Total time: {(time.perf_counter() - T_START) / 60:.1f} min')
'''),
]

# ---------------------------------------------------------------------------
# Baseline notebook (L4x4)
# ---------------------------------------------------------------------------

def baseline_cells(task_ids, files, hints=None):
    hint_code = ('import dataclasses\n'
                 'HINTS = ' + repr(hints) + '\n'
                 'tasks = [dataclasses.replace(t, hints_text=HINTS[t.instance_id]) for t in tasks]\n'
                 "print('ORACLE: correct-location hints added to', len(HINTS), 'tasks')\n") if hints else ''
    return [
    md(f'''
# Agent run on practice tasks, timed

**Why this notebook exists.** Every improvement needs a number to beat. This runs our agent (the config in the
repo's `submission/` folder, which is exactly what we submit) on {len(task_ids)} trusted practice tasks and records,
per task: solved or not, time, tool calls and model calls. It also saves every agent transcript.

Each task is also graded with its **gold patch** first, so we know the task itself can pass in this environment.
'''),
    md('## 1. Install the harness from the wheelhouse (offline)'),
    SETUP,
    HARDWARE,
    md('## 2. Agent config from our repo, and the task list'),
    agent_cell(files),
    code(r'''
from swegemma.models import load_tasks

TASK_IDS = ''' + repr(task_ids) + r'''

all_tasks = {t.instance_id: t for t in load_tasks(DATA_DIR / 'tasks.jsonl')}
tasks = [all_tasks[i] for i in TASK_IDS]
''' + hint_code + r'''print('Tasks:', [t.instance_id for t in tasks])
'''),
    md('## 3. Start the vLLM server (Gemma 4 across the GPUs)\nSame settings as scoring: 32,768-token context and the Gemma 4 tool-call parser. Loading the 31B model takes several minutes.'),
    code(r'''
import litellm
import torch
from adk_submission import VllmConfig, VllmServer, discover_adapters
from adk_submission.discovery import discover_declared_models
from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS

litellm.drop_params = True
t_vllm = time.perf_counter()

declared = discover_declared_models(AGENT_DIR)
assert len(declared) == 1, f'Expected 1 declared model, got {sorted(declared)}'
declared_model = next(iter(declared))
MODEL_PATH = find_input(f'/kaggle/input/models/google/gemma-4/other/{declared_model}/2',
                        f'/kaggle/input/gemma-4/other/{declared_model}/2')

adapters = discover_adapters(str(AGENT_DIR), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
adapter_map = getattr(adapters, 'adapters', None) or {}
ranks = [r for info in adapter_map.values() if (r := getattr(info, 'rank', None))]

gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 1
tp_size = 4 if gpu_count >= 4 else (2 if gpu_count >= 2 else 1)
extra = {'gemma-4-12b-it-qat-w4a16-ct': ('--hf-overrides', '{"architectures": ["Gemma4ForCausalLM"], "model_type": "gemma4"}')}

server = VllmServer(VllmConfig(
    model=str(MODEL_PATH), port=8000, host='127.0.0.1',
    tool_call_parser='gemma4', reasoning_parser='gemma4', max_model_len=32768,
    dtype='bfloat16' if (torch.cuda.is_available() and torch.cuda.is_bf16_supported()) else 'auto',
    gpu_memory_utilization=0.90, enable_auto_tool_choice=True,
    enable_lora=bool(adapter_map), max_loras=max(1, len(adapter_map)),
    max_lora_rank=max(ranks) if ranks else 128, scheduler_reserve_full_isl=False,
    tensor_parallel_size=tp_size, startup_timeout=60 * 20,
    extra_args=extra.get(declared_model, ()),
), adapter_manifest=adapters)
server.start()
models = server.create_model_registry(aliases=[declared_model], model_prefix='openai/',
                                      api_key=os.environ.get('LOCAL_API_KEY', 'EMPTY'))
VLLM_SECONDS = time.perf_counter() - t_vllm
print(f'vLLM ready on {gpu_count} GPU(s), tp={tp_size}, adapters={list(adapter_map)}, in {VLLM_SECONDS:.0f}s')
'''),
    md('## 4. Configure the evaluator (same settings as scoring)'),
    code(r'''
import yaml
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps._configs import EventsCompactionConfig
from swegemma.config import EvalConfig, build_submission_limits
from swegemma.evaluate import Evaluator

ev = yaml.safe_load((AGENT_DIR / 'eval_config.yaml').read_text())['evaluation']
limits, gen_constraints = build_submission_limits()
eval_config = EvalConfig(
    tasks_path=DATA_DIR / 'tasks.jsonl', snapshots_dir=DATA_DIR / 'snapshots',
    results_dir=RESULTS, submission_dir=AGENT_DIR, models=models, sandbox='subprocess',
    timeout_seconds=int(ev['timeout_seconds']), verification_timeout_seconds=300,
    max_time_minutes=float(ev['max_time_minutes']), max_tool_calls=int(ev['max_tool_calls']),
    max_turns=None, limits=limits, generation_constraints=gen_constraints, adapter_manifest=adapters,
    context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
    events_compaction_config=EventsCompactionConfig(compaction_interval=15, overlap_size=2,
                                                    token_threshold=14336, event_retention_size=5),
    graph_dir=str(DATA_DIR / 'graphs'), embeddings_dir=str(DATA_DIR / 'embeddings'),
    wheels_dir=DATA_DIR / 'wheels', verbose=False,
)
evaluator = Evaluator(eval_config)
'''),
    RUN_SYNC,
    CONTROL_FN,
    md('## 5. For each task: gold check, then the agent'),
    code(r'''
rows = []
for i, task in enumerate(tasks, start=1):
    gold = run_sync(grade_patch, evaluator, eval_config, task, task.patch)
    print(f'[{i}/{len(tasks)}] {task.instance_id}: gold patch {"PASSES" if gold["resolved"] else "FAILS"} ({gold["seconds"]}s)')

    t0 = time.perf_counter()
    r = run_sync(evaluator.evaluate_task, task=task, task_index=i, total_tasks=len(tasks))
    patch = (r.agent_patch or '').strip()
    (RESULTS / 'patches').mkdir(exist_ok=True)
    (RESULTS / 'patches' / f'{task.instance_id}.patch').write_text(patch)
    row = {'instance_id': task.instance_id, 'gold_resolved': gold['resolved'],
           'agent_resolved': bool(r.resolved), 'seconds': round(time.perf_counter() - t0, 1),
           'tool_calls': r.tool_calls, 'llm_calls': getattr(r, 'total_llm_calls', None),
           'patch_lines': len(patch.splitlines()), 'error': (r.error or '')[:200],
           'trace': str(r.trace_json_path or '')}
    rows.append(row)
    print(f"   agent: {'SOLVED' if row['agent_resolved'] else 'not solved'} | {row['seconds']}s | "
          f"{row['tool_calls']} tool calls | {row['llm_calls']} model calls | patch {row['patch_lines']} lines {row['error'][:80]}")
    with (RESULTS / 'baseline.jsonl').open('a') as f:
        f.write(json.dumps(row) + '\n')
'''),
    md('## 6. Summary'),
    code(r'''
import pandas as pd

df = pd.DataFrame(rows)
df.to_csv(RESULTS / 'baseline.csv', index=False)
print(df[['instance_id', 'gold_resolved', 'agent_resolved', 'seconds', 'tool_calls', 'llm_calls', 'patch_lines']])
fair = df[df['gold_resolved']]
print(f'\nSolved {int(fair["agent_resolved"].sum())} of {len(fair)} tasks whose gold patch passes')
print(f'Average time per task: {df["seconds"].mean():.0f}s | vLLM startup: {VLLM_SECONDS:.0f}s')
print(f'Total notebook time: {(time.perf_counter() - T_START) / 60:.1f} min')
server.stop()
'''),
]


def submit_cells(files):
    return [
    md('''
# Package submission.zip

**Why this notebook exists.** A submission is a notebook whose output is `submission.zip`. Kaggle then runs that
zip on its scoring machines against the hidden tasks. This notebook builds the zip from our repo's `submission/`
folder and checks it with the harness's own validator first, so a mistake cannot cost a daily submission.
'''),
    md('## 1. Install the harness (we need its validator)'),
    SETUP,
    md('## 2. Agent config from our repo'),
    agent_cell(files),
    md('## 3. Validate and zip'),
    code(r'''
import zipfile
from adk_submission import validate_directory
from adk_submission.discovery import discover_declared_models
from swegemma.config import ALLOWED_SUBMISSION_EXTENSIONS, MAX_SUBMISSION_SIZE_BYTES, build_submission_limits

limits, _ = build_submission_limits()
for dirpath, dirnames, filenames in os.walk(AGENT_DIR, followlinks=False):
    for name in (*dirnames, *filenames):
        assert not (Path(dirpath) / name).is_symlink(), f'Symlinks are not allowed: {name}'
validate_directory(AGENT_DIR, limits=limits)
declared = discover_declared_models(AGENT_DIR)
assert len(declared) == 1, f'Every agent must use the same model, found {sorted(declared)}'
print('Model:', next(iter(declared)))

zip_path = Path(shutil.make_archive(str(WORK / 'submission'), 'zip', root_dir=AGENT_DIR))
with zipfile.ZipFile(zip_path) as zf:
    infos = zf.infolist()
    assert 'agent.yaml' in zf.namelist(), 'agent.yaml must be at the root of the zip'
    assert sum(i.file_size for i in infos) <= MAX_SUBMISSION_SIZE_BYTES, 'Over the 3 GiB limit'
    for i in infos:
        if not i.is_dir():
            assert Path(i.filename).suffix.lower() in ALLOWED_SUBMISSION_EXTENSIONS, f'Bad file type: {i.filename}'
    print('\n'.join(sorted(zf.namelist())))

shutil.rmtree(AGENT_DIR)          # leave only submission.zip in the output
shutil.rmtree(RESULTS, ignore_errors=True)
print(f'\nCreated {zip_path} ({zip_path.stat().st_size / 1024:.0f} KiB)')
'''),
    ]


def write_notebook(cells, path):
    nb = {
        'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                     'language_info': {'name': 'python'}},
        'nbformat': 4, 'nbformat_minor': 4,
        'cells': cells,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(nb, indent=1), encoding='utf-8')
    print('wrote', path)


# One notebook per experiment arm: the agent folder, optional single-file overrides, optional ORACLE hints.
EXPERIMENTS = REPO / 'experiments'
ARMS = {
    'oracle': {'kernel': 'oracle', 'root': REPO / 'submission', 'hints': EXPERIMENTS / 'oracle' / 'hints.json'},
    'e3_1_r2': {'kernel': 'e3-1-r2', 'root': REPO / 'submission',
                'overrides': {'prompts/system.md': EXPERIMENTS / 'e3_1' / 'system_v2_1.md'}},
    'e5': {'kernel': 'e5', 'root': EXPERIMENTS / 'e5' / 'submission'},
    'e5_r2': {'kernel': 'e5-r2', 'root': EXPERIMENTS / 'e5' / 'submission'},
    'e5b': {'kernel': 'e5b', 'root': EXPERIMENTS / 'e5b' / 'submission'},
    'e5b_r2': {'kernel': 'e5b-r2', 'root': EXPERIMENTS / 'e5b' / 'submission'},
    'oracle_r2': {'kernel': 'oracle-r2', 'root': REPO / 'submission', 'hints': EXPERIMENTS / 'oracle' / 'hints.json'},
    # Week of Oct 31: held-out confirmation on 41 tasks (amendment A9); ORACLE hints name files only.
    'e2_h41': {'kernel': 'e2-h41', 'root': REPO / 'submission', 'tasks': 'heldout41'},
    'e3_1_h41': {'kernel': 'e3-1-h41', 'root': REPO / 'submission', 'tasks': 'heldout41',
                 'overrides': {'prompts/system.md': EXPERIMENTS / 'e3_1' / 'system_v2_1.md'}},
    'e5b_h41': {'kernel': 'e5b-h41', 'root': EXPERIMENTS / 'e5b' / 'submission', 'tasks': 'heldout41'},
    'oracle_h41': {'kernel': 'oracle-h41', 'root': REPO / 'submission', 'tasks': 'heldout41',
                   'hints': EXPERIMENTS / 'oracle' / 'hints_heldout41.json'},
    'e6': {'kernel': 'e6', 'root': EXPERIMENTS / 'e6' / 'submission'},
    'e6_r2': {'kernel': 'e6-r2', 'root': EXPERIMENTS / 'e6' / 'submission'},
}


def analysis_source(name):
    """An analysis module's functions, embedded so the Kaggle notebook runs the same code as our tests."""
    text = (REPO / 'analysis' / f'{name}.py').read_text(encoding='utf-8')
    text = text.split("\nif __name__ == '__main__':")[0].replace('from gold import', '# from gold import')
    return text.replace('Path(__file__).resolve().parent.parent', "Path('.')")   # notebook cells have no __file__


def graph_probe_cells(task_ids):
    """Gate G3 (CPU only): does graph search find the gold files as often as grep, from names in the issue?"""
    return [
    md('''
# Graph vs grep: can the code-graph tools find the right file? (gate G3)

**Why this notebook exists.** E6 asks Gemma's finder to locate bugs with the competition's graph tools instead of
`grep`. Before spending GPU on that, this checks the tools themselves, with no model involved: for each practice bug,
take the code names mentioned in the issue, ask `search_similar_code` and `grep` for them, and see whether the files
that the real fix changes appear in each method's top 5. Pass: graph hit rate at least grep's.
'''),
    SETUP,
    HARDWARE,
    code(r'''
import re
import subprocess
import tempfile
from collections import defaultdict
from swegemma.models import load_tasks
from swegemma.context import SwegemmaContext
from swegemma.tools import graph as graph_tools
from swegemma.deduplication import resolve_task_snapshot_paths, reconstruct_snapshot

''' + analysis_source('gold') + '\n' + analysis_source('issue_symbols') + r'''

TASK_IDS = ''' + repr(task_ids) + r'''
all_tasks = {t.instance_id: t for t in load_tasks(DATA_DIR / 'tasks.jsonl')}
print('snapshots dir sample:', sorted(p.name for p in (DATA_DIR / 'snapshots').iterdir())[:6])
print('graphs dir sample:', sorted(p.name for p in (DATA_DIR / 'graphs').iterdir())[:6])


def checkout(task):
    """The repository at the task's base commit, rebuilt the same way the harness does."""
    out = Path(tempfile.mkdtemp(prefix=task.instance_id + '_'))
    snap, base, patch = resolve_task_snapshot_paths(DATA_DIR / 'snapshots', task.instance_id, task.repo)
    if base and Path(base).exists():          # deduplicated layout: shared base archive + per-task patch
        ok = reconstruct_snapshot(base, patch if patch and Path(patch).exists() else None, out, fallback_path=snap)
        assert ok, f'could not rebuild {task.instance_id}'
    else:                                     # practice data: one standalone <task>.tgz per task
        import tarfile
        with tarfile.open(snap) as tar:
            tar.extractall(out, filter='data')
    return out


def py_files(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob('*.py'))


def node_to_file(node, files):
    """Longest dotted prefix of a graph node name that is a .py file in the repo."""
    parts = node.split('.')
    for i in range(len(parts), 0, -1):
        target = '/'.join(parts[:i]) + '.py'
        match = [f for f in files if f == target or f.endswith('/' + target)]
        if match:
            return match[0]
    return None


def graph_top5(task, symbols, files):
    ctx = SwegemmaContext(task=task, graph_dir=str(DATA_DIR / 'graphs'), embeddings_dir=str(DATA_DIR / 'embeddings'))
    best = defaultdict(float)
    for s in symbols:
        res = json.loads(graph_tools.search_similar_code(ctx, s, k=5))
        if res.get('status') != 'ok':
            print('  graph error for', s, ':', str(res)[:160])
            continue
        for r in res.get('results', []):
            f = node_to_file(r.get('node_name', ''), files)
            if f:
                best[f] = max(best[f], float(r.get('similarity') or 0))
    return [f for f, _ in sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))][:5]


def grep_top5(root, symbols):
    counts = defaultdict(int)
    for s in symbols:
        key = s.split('.')[-1]                       # what a developer would grep for
        out = subprocess.run(['grep', '-rlF', '--include=*.py', key, '.'], cwd=root, capture_output=True, text=True).stdout
        for f in out.split():
            counts[f.removeprefix('./')] += 1
    return [f for f, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))][:5]


def hit(gold_files, top):
    return bool(gold_files) and all(any(t == g or t.endswith('/' + g) for t in top) for g in gold_files)


rows = []
for i, tid in enumerate(TASK_IDS, 1):
    task = all_tasks[tid]
    gold = gold_locations(task.patch)['files']
    symbols = issue_symbols(task.problem_statement)
    root = checkout(task)
    files = py_files(root)
    g, r = graph_top5(task, symbols, files), grep_top5(root, symbols)
    rows.append({'instance_id': tid, 'symbols': symbols, 'gold_files': gold, 'graph_top5_files': g,
                 'graph_hit': hit(gold, g), 'grep_top5_files': r, 'grep_hit': hit(gold, r)})
    print(f"[{i}/{len(TASK_IDS)}] {tid}: graph {'HIT' if rows[-1]['graph_hit'] else 'miss'} | "
          f"grep {'HIT' if rows[-1]['grep_hit'] else 'miss'} | symbols {symbols}")
    shutil.rmtree(root, ignore_errors=True)

import pandas as pd
df = pd.DataFrame(rows)
df.to_csv(RESULTS / 'graph_probe.csv', index=False)
gr, gp = df['graph_hit'].mean(), df['grep_hit'].mean()
print(f'\ngraph hit rate {gr:.0%} ({df.graph_hit.sum()}/{len(df)}) | grep hit rate {gp:.0%} ({df.grep_hit.sum()}/{len(df)})')
print('G3', 'PASS: E6 runs graph-only' if gr >= gp else 'FAIL: E6 runs graph-first (graph calls, then grep)')
'''),
]


def build_arm(name):
    if name == 'graph_probe':
        out = HERE / name / f'{name}.ipynb'
        write_notebook(graph_probe_cells(PRACTICE30), out)
        meta = json.loads((HERE / 'controls' / 'kernel-metadata.json').read_text(encoding='utf-8'))
        meta.update(id='karthickbalaje/gemma4-graph-probe', title='gemma4-graph-probe', code_file=out.name,
                    enable_gpu=False, model_sources=[])
        meta.pop('machine_shape', None)
        (out.parent / 'kernel-metadata.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
        return out
    arm = ARMS[name]
    files = submission_files(arm['root'], arm.get('overrides'))
    hints = json.loads(arm['hints'].read_text(encoding='utf-8')) if arm.get('hints') else None
    out = HERE / name / f'{name}.ipynb'
    task_ids = json.loads((EXPERIMENTS / f"{arm['tasks']}.json").read_text()) if arm.get('tasks') else PRACTICE30
    write_notebook(baseline_cells(task_ids, files, hints), out)
    meta = json.loads((HERE / 'practice30' / 'kernel-metadata.json').read_text(encoding='utf-8'))
    meta.update(id=f"karthickbalaje/gemma4-{arm['kernel']}", title=f"gemma4-{arm['kernel']}", code_file=out.name)
    (out.parent / 'kernel-metadata.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    return out


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--arm':
        build_arm(sys.argv[2])
        sys.exit()
    files = submission_files(REPO / 'submission')
    write_notebook(controls, HERE / 'controls' / 'controls.ipynb')
    write_notebook(baseline_cells(BASELINE_TASK_IDS, files), HERE / 'baseline' / 'baseline.ipynb')
    write_notebook(baseline_cells(PRACTICE30, files), HERE / 'practice30' / 'practice30.ipynb')
    write_notebook(submit_cells(files), HERE / 'submit' / 'submit.ipynb')
