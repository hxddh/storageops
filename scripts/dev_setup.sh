#!/usr/bin/env bash
# One-shot developer setup: Python editable install, Node >= 22.19 on PATH,
# storageops install, and a doctor readiness check.
set -euo pipefail
cd "$(dirname "$0")/.."

USE_VENV=1
SKIP_INSTALL=0
PERSIST_PATH=0
VERIFY=0
NVM_BIN=""
PYTHON_BIN_PREFIX=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      USE_VENV=0
      shift
      ;;
    --skip-storageops-install)
      SKIP_INSTALL=1
      shift
      ;;
    --persist-path)
      PERSIST_PATH=1
      shift
      ;;
    --verify)
      VERIFY=1
      shift
      ;;
    -h|--help)
      echo "Usage: bash scripts/dev_setup.sh [OPTIONS]"
      echo "  --user                     pip install -e '.[dev]' to user site (~/.local/bin)"
      echo "  --skip-storageops-install  skip storageops install --force (offline only)"
      echo "  --persist-path             append PATH hints to ~/.bashrc (idempotent)"
      echo "  --verify                   run make ci-local after setup"
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

min_node_major=22
min_node_minor=19
STORAGEOPS_PATH_MARKER="# storageops-dev-setup"

persist_path_line() {
  local line="$1"
  touch "$HOME/.bashrc"
  if ! grep -Fq "$line" "$HOME/.bashrc" 2>/dev/null; then
    echo "$line  $STORAGEOPS_PATH_MARKER" >> "$HOME/.bashrc"
    echo "[ok] persisted: $line"
  fi
}

node_triple() {
  node --version 2>/dev/null | sed -n 's/^v\?\([0-9]*\)\.\([0-9]*\)\.\([0-9]*\).*/\1 \2 \3/p'
}

node_ok() {
  read -r major minor patch <<< "$(node_triple)" || return 1
  [[ -n "${major:-}" ]] || return 1
  if (( major > min_node_major )); then return 0; fi
  if (( major == min_node_major && minor >= min_node_minor )); then return 0; fi
  return 1
}

prepend_nvm_node() {
  local nvm_root="${NVM_DIR:-$HOME/.nvm}/versions/node"
  [[ -d "$nvm_root" ]] || return 1
  local best=""
  local best_ver=""
  for dir in "$nvm_root"/*; do
    [[ -d "$dir/bin" && -x "$dir/bin/node" ]] || continue
    local ver="${dir##*/}"
    ver="${ver#v}"
    IFS=. read -r major minor patch <<< "$ver"
    [[ -n "${major:-}" ]] || continue
    if (( major > min_node_major || (major == min_node_major && minor >= min_node_minor) )); then
      if [[ -z "$best_ver" || "$ver" > "$best_ver" ]]; then
        best="$dir/bin"
        best_ver="$ver"
      fi
    fi
  done
  if [[ -n "$best" ]]; then
    NVM_BIN="$best"
    export PATH="$best:$PATH"
    return 0
  fi
  return 1
}

echo "=== Python dev install ==="
if [[ "$USE_VENV" == 1 ]]; then
  if ! python3 -m venv .venv 2>/dev/null; then
    echo "[warn] python3 -m venv failed (install python3-venv); falling back to --user install"
    USE_VENV=0
  fi
fi
if [[ "$USE_VENV" == 1 ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install -U pip
  python -m pip install -e '.[dev]'
  PYTHON_BIN_PREFIX="$(pwd)/.venv/bin"
  export PATH="${PYTHON_BIN_PREFIX}:$PATH"
else
  python3 -m pip install -U pip
  python3 -m pip install -e '.[dev]'
  PYTHON_BIN_PREFIX="$HOME/.local/bin"
  export PATH="${PYTHON_BIN_PREFIX}:$PATH"
fi

echo "=== Node.js (need >= ${min_node_major}.${min_node_minor}) ==="
if ! node_ok; then
  if prepend_nvm_node && node_ok; then
    echo "[ok] using nvm Node $(node --version) on PATH"
  else
    echo "[error] Node $(node --version 2>/dev/null || echo 'not found') is too old for Pi Coding Agent." >&2
    echo "        Install Node >= ${min_node_major}.${min_node_minor} (e.g. nvm install 22) and re-run." >&2
    exit 1
  fi
else
  echo "[ok] Node $(node --version)"
fi

if [[ "$PERSIST_PATH" == 1 ]]; then
  echo "=== Persist PATH hints ==="
  if [[ -n "$PYTHON_BIN_PREFIX" ]]; then
    persist_path_line "export PATH=\"${PYTHON_BIN_PREFIX}:\$PATH\""
  fi
  if [[ -n "$NVM_BIN" ]]; then
    persist_path_line "export PATH=\"${NVM_BIN}:\$PATH\""
  fi
fi

if [[ "$SKIP_INSTALL" != 1 ]]; then
  echo "=== storageops install --force ==="
  storageops install --force
else
  echo "=== skipping storageops install (--skip-storageops-install) ==="
fi

echo "=== storageops doctor ==="
storageops doctor || true

if [[ "$VERIFY" == 1 ]]; then
  echo "=== make ci-local (--verify) ==="
  make ci-local
fi

echo
echo "Dev setup complete. Before opening a PR, run:"
echo "  make ci-local"
echo "With a model key configured, also run:"
echo "  make live-smoke"
