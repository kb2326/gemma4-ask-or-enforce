#!/bin/sh
# Local copy of the competition harness, for checking agent configs without a GPU.
# Same packages as the Kaggle wheelhouse: the three harness wheels from data/harness plus google-adk 1.36.1.
set -e
cd "$(dirname "$0")/.."
python -m venv .venv-harness
PY=.venv-harness/Scripts/python
[ -x "$PY" ] || PY=.venv-harness/bin/python
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q google-adk==1.36.1 litellm data/harness/adk_eval_core-0.1.0-py3-none-any.whl \
    data/harness/adk_submission-0.2.13-py3-none-any.whl data/harness/swegemma-0.2.11-py3-none-any.whl
"$PY" -c "import swegemma, adk_submission, google.adk; print('harness venv ready, google-adk', google.adk.__version__)"
