"""Gate G1: check agent folders with the competition's own validator and compiler, without a GPU.

Run with the harness venv (sh tools/setup_harness_venv.sh):
    .venv-harness/Scripts/python tools/check_submission.py submission experiments/e5/submission
Prints OK <dir> per folder; exits 1 if any folder fails.

Adapter weights exist only on Kaggle, so the adapter list is a stand-in (names from the sample submission).
Prompts may contain no braces except the allowed templates, because ADK treats {name} as a state variable.
"""

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'notebooks'))
from build_notebooks import submission_files  # noqa: E402  (same files the notebooks embed)

ALLOWED_TEMPLATES = {'{problem_description}', '{hints?}', '{localization?}'}
TOOL_NAMES = ['run_command', 'read_file', 'write_file', 'edit_file', 'submit_patch', 'get_status',
              'get_code_neighbors', 'search_similar_code', 'get_code_subgraph']
MODEL = 'gemma-4-31b-it-qat-w4a16-ct'


def materialize(folder):
    """The agent folder exactly as the notebooks build it (official sample filled in), in a temp directory."""
    out = Path(tempfile.mkdtemp(prefix='agent_'))
    for rel, text in submission_files(Path(folder)).items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(text, encoding='utf-8')
    return out


def brace_errors(folder):
    errors = []
    for p in sorted(Path(folder).rglob('*.md')):
        for m in re.finditer(r'\{[^{}\n]*\}|[{}]', p.read_text(encoding='utf-8')):
            if m.group() not in ALLOWED_TEMPLATES:
                errors.append(f'{p.as_posix()}: brace {m.group()!r} is not an allowed template')
    return errors


def compile_folder(folder):
    folder = materialize(folder)
    from adk_submission import compile_submission
    from adk_submission.discovery import AdapterInfo, AdapterManifest, discover_declared_models, validate_directory
    from adk_submission.registry import ModelRegistry
    from google.adk.models.lite_llm import LiteLlm
    from swegemma.config import build_submission_limits
    from swegemma.harness.agent_runner import resolve_swegemma_adapter

    def stub(name):
        def tool(arg: str = '') -> dict:
            return {}
        tool.__name__ = name
        return tool

    limits, constraints = build_submission_limits()
    validate_directory(folder, limits)
    declared = discover_declared_models(folder)
    if len(declared) != 1:
        raise ValueError(f'expected exactly 1 declared model, got {sorted(declared)}')
    registry = ModelRegistry()
    registry.register(MODEL, LiteLlm(model=f'openai/{MODEL}', api_base='http://127.0.0.1:8000/v1'))
    manifest = AdapterManifest(adapters={n: AdapterInfo(name=n, path=Path(n), format='peft', size_bytes=1)
                                         for n in ('main_lora', 'tool_lora')})
    return compile_submission(folder, {n: stub(n) for n in TOOL_NAMES}, registry, limits=limits,
                              generation_constraints=constraints, adapter_manifest=manifest,
                              adapter_resolver_fn=lambda base, info: resolve_swegemma_adapter(base, info, registry))


def describe(agent, depth=0):
    tools = [getattr(t, '__name__', getattr(t, 'name', '?')) for t in getattr(agent, 'tools', []) or []]
    line = f"{'  ' * depth}{type(agent).__name__} {agent.name}"
    if tools:
        line += f" tools={tools}"
    if getattr(agent, 'output_key', None):
        line += f" output_key={agent.output_key}"
    print(line)
    for sub in getattr(agent, 'sub_agents', []) or []:
        describe(sub, depth + 1)


def main(folders):
    failed = False
    for folder in folders:
        errors = brace_errors(materialize(folder))
        if not errors:
            try:
                describe(compile_folder(folder), 1)
            except Exception as e:  # report every folder, then fail
                errors = [f'{type(e).__name__}: {e}']
        if errors:
            failed = True
            print(f'FAIL {folder}')
            for e in errors:
                print(f'  {e}')
        else:
            print(f'OK {folder}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
