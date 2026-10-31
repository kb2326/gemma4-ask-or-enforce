"""Gate G2: run the compiled E5/E6 pipeline in real ADK with a scripted fake model (no GPU, no real tools).

Run with the harness venv:
    .venv-harness/Scripts/python tools/sim_pipeline.py experiments/e5/submission
Checks that (1) the localizer's answer reaches the fixer's instruction through {localization?}, (2) the harness's
task message reaches the fixer, and counts (3) how many times the localizer runs when the harness sends a
continuation nudge because the fixer stopped without submit_patch. Exits 1 if (1) or (2) fails.
"""

import asyncio
import sys

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from check_submission import compile_folder

TASK_MESSAGE = 'TASK-MESSAGE: fix the bug in rich. 5. As your final action, return a text-only response.'
NUDGE = 'Please continue your work using the available tools, or call submit_patch when you have completed the task.'
FINDINGS = 'FILES: rich/console.py | FUNCTIONS: render | PLAN: handle the empty case'
seen = {'localizer_runs': 0, 'fixer_instructions': [], 'fixer_contents': []}


class ScriptedModel(BaseLlm):
    """Localizer: one read_file call, then its findings. Fixer: stops without submitting once, then submits."""
    role: str = ''

    async def generate_content_async(self, request, stream=False):
        texts = [p.text or '' for c in request.contents for p in c.parts]
        own_calls = sum(1 for c in request.contents for p in c.parts
                        if p.function_call and c.role == 'model')
        if self.role == 'localizer':
            has_tools = bool(request.config and request.config.tools)
            last_is_tool_result = request.contents and any(p.function_response for p in request.contents[-1].parts)
            if not has_tools:                       # E5b: a tool-less localizer answers in one step
                seen['localizer_runs'] += 1
                yield LlmResponse(content=types.Content(role='model', parts=[types.Part(text=FINDINGS)]))
            elif not last_is_tool_result:
                seen['localizer_runs'] += 1
                yield LlmResponse(content=types.Content(role='model', parts=[types.Part(
                    function_call=types.FunctionCall(name='read_file', args={}))]))
            else:
                yield LlmResponse(content=types.Content(role='model', parts=[types.Part(text=FINDINGS)]))
            return
        seen['fixer_instructions'].append(str(request.config.system_instruction or ''))
        seen['fixer_contents'].append(' '.join(texts))
        if NUDGE not in ' '.join(texts):
            yield LlmResponse(content=types.Content(role='model', parts=[types.Part(text='I think it is fixed.')]))
        elif own_calls == 0 or not any(p.function_response and p.function_response.name == 'submit_patch'
                                       for c in request.contents for p in c.parts):
            yield LlmResponse(content=types.Content(role='model', parts=[types.Part(
                function_call=types.FunctionCall(name='submit_patch', args={}))]))
        else:
            yield LlmResponse(content=types.Content(role='model', parts=[types.Part(text='Submitted.')]))


def swap_models(agent):
    if hasattr(agent, 'model') and agent.name in ('localizer', 'fixer'):
        agent.model = ScriptedModel(model='scripted', role=agent.name)
    for sub in getattr(agent, 'sub_agents', []) or []:
        swap_models(sub)


async def simulate(folder):
    root = compile_folder(folder)
    swap_models(root)
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name='sim', user_id='u', state={'problem_description': 'BUG'})
    runner = Runner(app_name='sim', agent=root, session_service=sessions)
    for message in (TASK_MESSAGE, NUDGE):  # the harness nudges once because the fixer stopped without submitting
        async for _ in runner.run_async(user_id='u', session_id=session.id,
                                        new_message=types.Content(role='user', parts=[types.Part(text=message)])):
            pass


def main(folder):
    asyncio.run(simulate(folder))
    findings_reach_fixer = any(FINDINGS in i for i in seen['fixer_instructions'])
    task_reaches_fixer = any('TASK-MESSAGE' in c for c in seen['fixer_contents'])
    print(f'localization reaches the fixer instruction: {findings_reach_fixer}')
    print(f'task message reaches the fixer: {task_reaches_fixer}')
    print(f'localizer runs with one nudge: {seen["localizer_runs"]}')
    return 0 if findings_reach_fixer and task_reaches_fixer else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
