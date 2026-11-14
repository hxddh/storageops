#!/usr/bin/env bash
# End-to-end launch test: packaged wheel -> storageops install -> Pi session.
#
# Proves the three things v0.8.0 got wrong, without a model key or a bucket:
#   1. the extension loads (Pi no longer rejects the layout)
#   2. the diagnose session exposes only read-only tools (no bash/edit/write)
#   3. a contract-valid submit_diagnosis is accepted and recorded
#
# Requires network on first run (npm install of Pi) unless PI_BIN is set.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
WORK="$(mktemp -d)"
PORT="${STORAGEOPS_E2E_PORT:-18181}"

cleanup() {
  [[ -n "${MOCK_PID:-}" ]] && kill "$MOCK_PID" 2>/dev/null || true
  [[ -n "${SERVER_PID:-}" ]] && kill "$SERVER_PID" 2>/dev/null || true
  if [[ "${STORAGEOPS_E2E_KEEP:-}" == "1" ]]; then echo "kept: $WORK"; else rm -rf "$WORK"; fi
}
trap cleanup EXIT

echo "== build wheel =="
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install -q --upgrade pip build >/dev/null
"$WORK/venv/bin/pip" install -q -e '.[dev]' >/dev/null
python3 scripts/prepare_httpmon_vendor.py >/dev/null
"$WORK/venv/bin/python" -m build --wheel --outdir "$WORK/dist" >/dev/null
WHEEL="$(ls "$WORK"/dist/*.whl)"
"$WORK/venv/bin/pip" install -q "$WHEEL"

echo "== resolve pi =="
if [[ -n "${PI_BIN:-}" ]]; then
  PI="$PI_BIN"
else
  npm install -g --prefix "$WORK/pi" @earendil-works/pi-coding-agent@1.5.2 >/dev/null 2>&1
  PI="$WORK/pi/bin/pi"
fi
"$PI" --version

echo "== mock provider =="
python3 scripts/mock_provider.py --port "$PORT" --log "$WORK/requests.jsonl" &
MOCK_PID=$!
for _ in $(seq 1 50); do
  curl -s -o /dev/null "http://127.0.0.1:$PORT/" || true
  if kill -0 "$MOCK_PID" 2>/dev/null && curl -s -o /dev/null -X POST "http://127.0.0.1:$PORT/v1/chat/completions" -d '{}'; then break; fi
  sleep 0.1
done

echo "== install =="
export PATH="$(dirname "$PI"):$WORK/venv/bin:$PATH"
export STORAGEOPS_SKIP_VERSION_CHECK=1
export HOME="$WORK/home"
mkdir -p "$HOME"
storageops install >"$WORK/install.log" 2>&1 || { cat "$WORK/install.log"; exit 1; }
grep -q "extension ->" "$WORK/install.log"
test -f "$HOME/.storageops/agent/extensions/storageops/index.ts"
test ! -f "$HOME/.storageops/agent/extensions/storageops.ts"

cat > "$HOME/.storageops/agent/models.json" <<JSON
{"providers": {"mock": {"baseUrl": "http://127.0.0.1:$PORT/v1", "api": "openai-completions",
  "apiKey": "dummy", "models": [{"id": "mock-1", "contextWindow": 128000, "maxTokens": 4096}]}}}
JSON

echo "== run diagnose session =="
set +e
storageops --print --no-session --provider mock --model mock-1 "diagnose this endpoint" >"$WORK/out.txt" 2>"$WORK/err.txt"
CODE=$?
set -e
echo "exit=$CODE"
echo "--- stdout ---"; cat "$WORK/out.txt"
echo "--- stderr ---"; cat "$WORK/err.txt"
echo "--- requests ---"; wc -l < "$WORK/requests.jsonl"
if [[ $CODE -ne 0 ]]; then
  echo "--- stderr ---"; cat "$WORK/err.txt"; exit 1
fi
grep -q "## Summary" "$WORK/out.txt"
grep -Eq "root_cause_type=(tcp|dns|tls)" "$WORK/out.txt"
grep -q "## What Would Falsify This" "$WORK/out.txt"

echo "== assert tool surface and persona =="
"$WORK/venv/bin/python" - "$WORK/requests.jsonl" <<'PY'
import json, sys
lines = [json.loads(line) for line in open(sys.argv[1])]
lines = [line for line in lines if line.get("tools")]
assert lines, "no model request carried tools"
first = lines[0]
tools = {t["function"]["name"] for t in first.get("tools", [])}
required = {"probe_endpoint", "probe_bucket", "probe_capabilities", "run_analyzer", "submit_diagnosis", "search_cases"}
forbidden = {"bash", "edit", "write", "powershell"}
missing = required - tools
extra = forbidden & tools
assert not missing, f"missing tools: {sorted(missing)}"
assert not extra, f"write tools exposed: {sorted(extra)}"
system = " ".join(
    str(m.get("content")) for m in first["messages"] if m.get("role") in ("system", "developer")
)
assert "You are StorageOps" in system, "StorageOps persona missing from system prompt"
assert "capture_http_trace" in tools
print(f"tools ok ({len(tools)} exposed, 0 write tools, persona present)")
PY

echo "== assert case recorded =="
CASES="$(ls "$HOME"/.storageops/cases/*.json 2>/dev/null | wc -l)"
test "$CASES" -ge 1
"$WORK/venv/bin/python" - "$HOME" <<'PY'
import json, glob, sys
path = glob.glob(sys.argv[1] + "/.storageops/cases/*.json")[0]
record = json.load(open(path))
assert record["root_cause_type"] in {"tcp", "dns", "tls"}, record
assert record["contract_version"] == "2.0", record
assert "secret" not in json.dumps(record).lower()
print("case ok:", record["case_id"])
PY

echo "e2e mock: OK"
