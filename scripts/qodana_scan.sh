#!/bin/bash
# Runs Qodana on a copy of the project's source files on WSL's own filesystem.
#
# qodana.yaml `exclude` only filters the report; Qodana still indexes the whole
# checkout. Indexing the WhisperLive submodule makes it flag valid code such as
# `str | None` as "Invalid type annotation" by the hundred (see below), and it
# keeps that in its cache. The copy holds only our sources, and reading it from
# the Linux filesystem is faster than /mnt/<drive>. Extra arguments are passed
# to `qodana scan`.
set -euo pipefail

SRC=$(cd "$(dirname "$0")/.." && pwd)
WORK="$HOME/.cache/snapsolve-qodana"
DEST="$WORK/src"

cd "$SRC"
rm -rf "$DEST"
mkdir -p "$DEST"
# Tracked and new (not ignored) files. The WhisperLive submodule stays out: its
# setup.py declares python_requires=">=3.9", and once Qodana resolves it, it
# checks our type hints against 3.9 (where `str | None` is invalid).
git -c safe.directory='*' ls-files -co --exclude-standard \
    | grep -v '^services/whisperlive' \
    | tr -d '\r' | rsync -a --files-from=- . "$DEST/"

cd "$DEST"
# The interpreter is built by scripts/qodana_bootstrap.sh inside the cache dir.
NONINTERACTIVE=true qodana scan \
    --cache-dir "$WORK/cache" \
    --results-dir "$WORK/results" \
    --fail-threshold 0 \
    --print-problems \
    -e QODANA_PYTHON_PATH=/data/cache/snapsolve-venv/bin/python \
    "$@"
