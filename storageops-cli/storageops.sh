#!/bin/bash
# StorageOps CLI wrapper — run without pip install
CLI_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$CLI_DIR")"
PYTHONPATH="$CLI_DIR:$PYTHONPATH" python3 -m storageops.cli "$@"
