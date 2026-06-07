#!/usr/bin/env bash
# Run the extension behavioral tests the way CI's tool-tests job does: with a
# minimal typebox stub so Node can strip types and import storageops.ts without
# the real dependency. Closes the gap where `make validate` only greps the
# extension and never exercises detect_domain / provider / trace behavior.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v node >/dev/null 2>&1; then
  echo "node not found; install Node 22.19+ to run extension tests" >&2
  exit 1
fi

stub="node_modules/typebox"
if [ ! -e "$stub/index.js" ]; then
  mkdir -p "$stub"
  printf 'export const Type = new Proxy({}, { get: () => () => ({}) });\n' > "$stub/index.js"
  printf '{"name":"typebox","version":"0.0.0","type":"module","main":"index.js","exports":{".":"./index.js"}}\n' > "$stub/package.json"
fi

exec node --experimental-strip-types --test tests/extension/*.test.ts
