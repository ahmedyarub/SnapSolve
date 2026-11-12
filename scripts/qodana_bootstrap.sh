#!/bin/bash
# Qodana bootstrap: builds the Python 3.12 interpreter Qodana analyses against.
#
# Runs inside the Qodana container (project at /data/project, persistent cache
# at /data/cache). The venv is rebuilt only when the requirement files change.
# The scan must be started with
#   -e QODANA_PYTHON_PATH=/data/cache/snapsolve-venv/bin/python
# or Qodana falls back to an interpreter without the stdlib or dependencies and
# reports valid code (e.g. `str | None`) as invalid.
set -euo pipefail

VENV=/data/cache/snapsolve-venv
STAMP="$VENV/.requirements.sha256"
HASH=$(cat requirements.txt constraints-gpu.txt scripts/qodana_bootstrap.sh | sha256sum | cut -d' ' -f1)

if [ -x "$VENV/bin/python" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$HASH" ]; then
    echo "Qodana venv is up to date."
    exit 0
fi

echo "Building Qodana venv in $VENV..."
/opt/miniconda3/bin/python3 -m venv --clear "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip

# PyAudio needs PortAudio headers to build on Linux and is not needed for
# static analysis. Torch comes from the CPU index: the analysis needs its
# Python sources, not CUDA. scipy-stubs gives the analysis scipy's real
# return types.
grep -viE '^\s*pyaudio\s*$' requirements.txt > /tmp/qodana-requirements.txt
PIP_CACHE_DIR=/data/cache/pip "$VENV/bin/python" -m pip install --quiet \
    -r /tmp/qodana-requirements.txt \
    scipy-stubs \
    -c constraints-gpu.txt \
    --extra-index-url https://download.pytorch.org/whl/cpu

echo "$HASH" > "$STAMP"
echo "Qodana venv ready."
