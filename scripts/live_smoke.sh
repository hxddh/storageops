#!/usr/bin/env bash
# Live diagnosis smoke: model round-trip + golden-case eval for core flows.
# Requires storageops install, Node/Pi readiness, and a model provider API key.
set -euo pipefail
cd "$(dirname "$0")/.."

PROVIDER="${STORAGEOPS_PROVIDER:-deepseek}"
MODEL="${STORAGEOPS_MODEL:-deepseek-v4-pro}"
PROMPT="${STORAGEOPS_LIVE_PROMPT:-Diagnose the root cause and safe next steps}"

# Optional explicit key; otherwise storageops reads api-key file / env via doctor.
MODEL_KEY="${STORAGEOPS_MODEL_KEY:-}"

live_available() {
  storageops doctor --json 2>/dev/null | python3 -c \
    "import json,sys; print(json.load(sys.stdin).get('live_diagnosis_available', False))"
}

if [[ "$(live_available)" != "True" ]]; then
  echo "[error] Live diagnosis is not available." >&2
  echo "        Run: storageops doctor" >&2
  echo "        Configure: storageops configure --provider ${PROVIDER} --model ${MODEL} --api-key" >&2
  echo "        Or set STORAGEOPS_MODEL_KEY / DEEPSEEK_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY" >&2
  exit 1
fi

smoke_args=(smoke --provider "$PROVIDER" --model "$MODEL")
diag_args=(--provider "$PROVIDER" --model "$MODEL" --print)
if [[ -n "$MODEL_KEY" ]]; then
  smoke_args+=(--api-key "$MODEL_KEY")
  diag_args+=(--api-key "$MODEL_KEY")
fi

echo "=== storageops smoke ==="
storageops "${smoke_args[@]}"

CASES=(
  throttling-hot-prefix
  access-denied-cross-account
  signature-clock-skew
)

for case_name in "${CASES[@]}"; do
  case_dir="skills/storageops-eval-golden-cases/cases/${case_name}"
  if [[ ! -f "${case_dir}/expected.json" ]]; then
    echo "[error] missing golden case: ${case_name}" >&2
    exit 1
  fi
  input_file="$(ls "${case_dir}"/input/* 2>/dev/null | head -1 || true)"
  if [[ -z "$input_file" ]]; then
    echo "[error] no input file for case: ${case_name}" >&2
    exit 1
  fi
  out="/tmp/storageops-live-smoke-${case_name}.md"
  echo "=== live diagnosis: ${case_name} ==="
  storageops "${diag_args[@]}" @"${input_file}" "${PROMPT}" > "${out}"
  test -s "${out}"
  head -20 "${out}" || true
  python3 skills/storageops-eval-golden-cases/scripts/eval_runner.py \
    --case "${case_dir}" --output "${out}"
done

echo "live-smoke OK (${#CASES[@]} cases)"
