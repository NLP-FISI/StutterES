#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/src/clips_3s"
PY="../.venv/bin/python"

$PY build_index.py
$PY download_clips.py
$PY split_dataset.py
$PY stats.py
$PY verify_clips.py
