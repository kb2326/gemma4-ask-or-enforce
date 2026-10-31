"""Checks for notebooks/build_notebooks.py. Run: python notebooks/test_build.py"""

import ast
import json
import subprocess
import sys
from pathlib import Path

from build_notebooks import REPO, build_arm, submission_files

HERE = Path(__file__).parent
DOCKER = 'gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461'


def notebook_source(name):
    nb = json.loads((HERE / name / f'{name}.ipynb').read_text(encoding='utf-8'))
    return '\n'.join(''.join(c['source']) for c in nb['cells'])


def embedded(source, var):
    """Value of a `VAR = {...}` literal embedded in a notebook cell."""
    line = next(l for l in source.splitlines() if l.startswith(f'{var} = '))
    return ast.literal_eval(line[len(var) + 3:])


def test_oracle_embeds_hints_and_e2_files():
    build_arm('oracle')
    src = notebook_source('oracle')
    assert embedded(src, 'AGENT_FILES') == submission_files(REPO / 'submission')
    hints = json.loads((REPO / 'experiments' / 'oracle' / 'hints.json').read_text())
    assert embedded(src, 'HINTS') == hints and len(hints) == 30
    assert 'dataclasses.replace(t, hints_text=HINTS[t.instance_id])' in src


def test_e3_1_r2_overrides_prompt():
    build_arm('e3_1_r2')
    files = embedded(notebook_source('e3_1_r2'), 'AGENT_FILES')
    want = submission_files(REPO / 'submission')
    assert files['prompts/system.md'] == (REPO / 'experiments' / 'e3_1' / 'system_v2_1.md').read_text(encoding='utf-8')
    assert {k: v for k, v in files.items() if k != 'prompts/system.md'} == \
        {k: v for k, v in want.items() if k != 'prompts/system.md'}
    assert 'HINTS = ' not in notebook_source('e3_1_r2')


def test_metadata():
    build_arm('oracle')
    meta = json.loads((HERE / 'oracle' / 'kernel-metadata.json').read_text())
    assert meta['id'] == 'karthickbalaje/gemma4-oracle' and meta['title'] == 'gemma4-oracle'
    assert meta['code_file'] == 'oracle.ipynb' and meta['machine_shape'] == 'NvidiaL4'
    assert meta['docker_image'] == DOCKER


def test_agent_dir_keeps_only_sample_adapters():
    assert "if child.name != 'adapters'" in notebook_source('oracle')


def test_graph_probe_is_cpu_and_self_contained():
    build_arm('graph_probe')
    meta = json.loads((HERE / 'graph_probe' / 'kernel-metadata.json').read_text())
    assert meta['id'] == 'karthickbalaje/gemma4-graph-probe'
    assert meta['enable_gpu'] is False and 'machine_shape' not in meta and meta['model_sources'] == []
    src = notebook_source('graph_probe')
    assert 'def issue_symbols' in src and 'def gold_locations' in src      # analysis code embedded, not imported
    assert 'resolve_task_snapshot_paths' in src and 'search_similar_code' in src
    assert embedded(src, 'TASK_IDS') == json.loads((REPO / 'experiments' / 'practice30.json').read_text())
    nb = json.loads((HERE / 'graph_probe' / 'graph_probe.ipynb').read_text(encoding='utf-8'))
    for c in nb['cells']:
        if c['cell_type'] == 'code':
            compile(''.join(c['source']), 'graph_probe', 'exec')


def test_embedded_analysis_code_runs_without_file():
    """Notebook cells have no __file__; the embedded gold/issue_symbols code must still define its functions."""
    from build_notebooks import analysis_source
    ns = {}
    exec(analysis_source('gold') + '\n' + analysis_source('issue_symbols'), ns)
    assert ns['gold_locations']('+++ b/a/b.py\n@@ -1 +1 @@ def f(x):\n+y\n')['files'] == ['a/b.py']
    assert ns['issue_symbols']('`x_y`') == ['x_y']


def test_checkout_handles_standalone_snapshots():
    """Practice snapshots are standalone <task>.tgz files with no base snapshot (base is None on Kaggle)."""
    import io
    import tarfile
    import tempfile
    from build_notebooks import graph_probe_cells
    cell = ''.join(graph_probe_cells(['x'])[3]['source'])
    src = cell[cell.index('def checkout'):cell.index('def py_files')]
    tmp = Path(tempfile.mkdtemp())
    snap = tmp / 'x.tgz'
    with tarfile.open(snap, 'w:gz') as tar:
        data = b'print(1)\n'
        info = tarfile.TarInfo('workspace/pkg/mod.py')
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    ns = {'Path': Path, 'tempfile': tempfile, 'DATA_DIR': tmp,
          'resolve_task_snapshot_paths': lambda d, i, r: (snap, None, None),
          'reconstruct_snapshot': lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not be called'))}
    exec(src, ns)
    root = ns['checkout'](type('T', (), {'instance_id': 'x', 'repo': 'r'})())
    assert (root / 'workspace' / 'pkg' / 'mod.py').read_text() == 'print(1)\n'


def test_e5b_localizer_has_no_tools():
    build_arm('e5b')
    files = embedded(notebook_source('e5b'), 'AGENT_FILES')
    assert files == submission_files(REPO / 'experiments' / 'e5b' / 'submission')
    assert 'tools:' not in files['sub_agents/localizer.yaml'] and 'submit_patch' in files['sub_agents/fixer.yaml']
    assert json.loads((HERE / 'e5b' / 'kernel-metadata.json').read_text())['id'] == 'karthickbalaje/gemma4-e5b'


SAMPLE = REPO / 'data' / 'agent' / 'sample_submission'


def test_submission_is_sample_plus_our_changes():
    """The repo keeps only our own files; a folder without agent.yaml starts from the official sample."""
    files = submission_files(REPO / 'submission')
    assert files['prompts/system.md'] == (SAMPLE / 'prompts' / 'system.md').read_text(encoding='utf-8')
    assert files['agent.yaml'] == (SAMPLE / 'agent.yaml').read_text(encoding='utf-8')
    assert files['configs/sampling.yaml'] == (REPO / 'submission' / 'configs' / 'sampling.yaml').read_text(encoding='utf-8')
    assert 'max_output_tokens: 8192' in files['configs/sampling.yaml']


def test_fixer_marker_becomes_official_prompt():
    """fixer.md stores our preamble plus a marker; the builder inserts the official prompt in its place."""
    from build_notebooks import OFFICIAL_PROMPT_MARKER
    stored = (REPO / 'experiments' / 'e5' / 'submission' / 'prompts' / 'fixer.md').read_text(encoding='utf-8')
    assert OFFICIAL_PROMPT_MARKER in stored
    fixer = submission_files(REPO / 'experiments' / 'e5' / 'submission')['prompts/fixer.md']
    assert OFFICIAL_PROMPT_MARKER not in fixer and fixer.startswith('## You are step 2 of 2')
    assert (SAMPLE / 'prompts' / 'system.md').read_text(encoding='utf-8') in fixer
    assert 'agent.yaml' in submission_files(REPO / 'experiments' / 'e5' / 'submission')   # own agent.yaml, no sample base
    assert 'sub_agents/code_analyzer.yaml' not in submission_files(REPO / 'experiments' / 'e5' / 'submission')


def test_heldout_arms():
    """Week of Oct 31: the four arms run on the 41 held-out tasks; ORACLE hints name files only."""
    h41 = json.loads((REPO / 'experiments' / 'heldout41.json').read_text())
    assert len(h41) == 41 and len(set(h41)) == 41
    assert not set(h41) & set(json.loads((REPO / 'experiments' / 'practice30.json').read_text()))
    for arm, kernel in [('e2_h41', 'e2-h41'), ('e3_1_h41', 'e3-1-h41'), ('e5b_h41', 'e5b-h41'), ('oracle_h41', 'oracle-h41')]:
        build_arm(arm)
        src = notebook_source(arm)
        assert embedded(src, 'TASK_IDS') == h41, arm
        assert json.loads((HERE / arm / 'kernel-metadata.json').read_text())['id'] == f'karthickbalaje/gemma4-{kernel}'
    hints = embedded(notebook_source('oracle_h41'), 'HINTS')
    assert set(hints) == set(h41) and not any('Functions' in h for h in hints.values())
    assert embedded(notebook_source('e2_h41'), 'AGENT_FILES') == submission_files(REPO / 'submission')
    assert 'HINTS = ' not in notebook_source('e5b_h41')


def test_default_build_unchanged():
    out = subprocess.run([sys.executable, str(HERE / 'build_notebooks.py')], capture_output=True, text=True, check=True)
    assert out.stdout.count('wrote') == 4
    assert 'HINTS = ' not in notebook_source('practice30')


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
    print('all build tests passed')
