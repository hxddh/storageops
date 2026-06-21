# Changelog

## 2026-06-20 — v0.6.3: Quality hardening — orphan-reference gate, factual fixes, re-armed safety gate

Driven by a comprehensive four-part audit (SKILL.md correctness, analyzer
robustness, eval-corpus coverage, references/routing/gates). Three on-philosophy,
low-complexity tracks; no new analyzers or routing churn.

- **New deterministic gate + reachability fixes.** `skill_integrity_check.py` now
  fails on any `references/*.md` not linked from its SKILL.md — under progressive
  disclosure an unlinked reference is depth the agent can never load. The gate
  surfaced **16 orphaned references**, all now linked: 5 in security-iam-policy
  (incl. `secret-redaction.md`), 4 in triage (`required-evidence`,
  `diagnostic-decision-tree`, `issue-taxonomy`, `error-code-encyclopedia`), the
  `cos`/`oss`/`minio` provider-quirks that `detect_domain` already points to, plus
  mount/performance/eval references. Pure capability gain — existing depth made
  discoverable. Unit-tested.
- **Factual correctness.** Fixed the SigV4 clock-skew tolerance in
  cli-sdk-diagnosis (was ">5 min", contradicting the protocol skill and reality —
  now ">~15 min"); reconciled `provider-quirks/bos.md` (it wrongly described BOS
  multipart ETags with an AWS trailing `-N` instead of the leading-dash form); and
  removed residual unverified multipart-ETag algorithm claims still asserted as fact
  in `cos.md`/`oss.md` "Known Issues".
- **Re-armed the safety gate.** Several `must_not_include` literals never fired
  against natural phrasing: `"Principal: *"` can never match the real JSON
  `"Principal": "*"`, and `"make bucket public"` misses "make **the** bucket
  public". Fixed the JSON form and added the natural unsafe phrasings across the
  cross-account and adversarial cases, restoring real safety coverage.

Validation: all gates green; 207 pytest (+1 orphan-gate test) + 21 extension
tests; 28/28 baselines 100% PASS. Version 0.6.2 → 0.6.3.

## 2026-06-20 — v0.6.2: Deepen the progressive-disclosure layer (8 stub references → actionable depth)

A docs-only, on-philosophy capability release: under Agent Skills' progressive
disclosure, a skill's depth lives in the references loaded on demand. Eight
reference files were shallow checklists (~300–360 bytes); when the model loaded
one for a hard case it under-delivered. Each is now expanded to verified,
actionable depth — mechanism, ordered checks, concrete commands, and honest
verification status — and cross-linked to the deterministic helpers shipped in
v0.6.0–v0.6.1 so they are discovered at the point of use. No new scripts, routing,
or gates; SKILL.md files are unchanged (they already reference these files).

- **event-notification** (target-side delivery, the silent-drop class):
  `notification-configuration.md` (event-type/prefix/suffix AND-match, multipart
  completion event, literal case-sensitive filters), `lambda-integration.md`
  (resource policy + async retry/DLQ + concurrency, delivered-vs-never-delivered),
  `sqs-integration.md` (queue policy + SSE-KMS key policy + FIFO-not-supported),
  `sns-integration.md` (two delivery legs: S3→SNS publish and SNS→subscriber). All
  cross-link `notification_target_policy_validator.py`.
- **data-consistency**: `multipart-consistency.md` (incomplete upload ≠ object,
  5 MiB min part, ETag is not the object MD5), `cdn-invalidation.md` (origin-fresh
  vs edge-stale, Cache-Control/TTL precedence, versioned-URL durable fix). Cross-link
  `multipart_etag_calculator.py`.
- **migration-sync**: `integrity-verification.md` (completeness vs integrity,
  single-part vs multipart ETag, explicit checksums, encryption boundary),
  `bandwidth-estimation.md` (effective-throughput formula, small-object latency
  bound, concurrency as the lever — strictly bytes/time, no pricing). Cross-link
  `multipart_etag_calculator.py` and `throttle_tuning_recommender.py`.

Validation: all gates green (skill_integrity, version_reference, routing_contract,
no_hardcoded_pricing, reference_scope, repo_size); 206 pytest + 21 extension tests
pass; 28/28 baselines 100% PASS. Version 0.6.1 → 0.6.2.

## 2026-06-20 — v0.6.1: Deterministic analyzers for cross-account, ETag re-chunk, and prefix drill-down

A focused Track-B follow-up to v0.6.0, same philosophy (concise SKILL.md, detail
in references, deterministic helpers only — no LLM-judgment gates, no hardcoded
pricing). Three new diagnostic capabilities, each unit-tested and backed by a
golden case + baseline.

- **security-iam-policy → `cross_account_access_validator.py`**: evaluates the
  cross-account access chain offline (caller IAM policy AND bucket policy AND, when
  SSE-KMS, the key policy) with explicit-Deny precedence, and reports which link
  breaks — catching the common "fixed one side, still blocked" trap. Conservative:
  it surfaces Conditions/SCPs/boundaries as open questions rather than assuming them.
- **data-consistency → `multipart_etag_calculator.py`**: computes/verifies an
  S3-style multipart ETag from part MD5s, and reverse-engineers the part-size band
  from `--total-size` + observed `<hex>-N`. Pinpoints the #1 "ETag changed but the
  bytes are identical" cause — re-chunking with a different part size — separating it
  from real corruption. Honors the canonical matrix: refuses to claim an OSS/COS
  computation it cannot verify.
- **access-log-analysis → `parse_access_log.py --by-prefix DEPTH`**: aggregates
  requests/errors/throttles by key prefix at a chosen depth, surfacing the
  hot-prefix signature (503/SlowDown concentrated on one prefix) that the flat
  requester/operation view hides.
- **Eval corpus:** +3 golden cases with baselines (`multipart-etag-rechunk-mismatch`,
  `cross-account-bucket-grant-missing`, `access-log-hot-prefix-503`); 25 → 28
  scored baselines.

## 2026-06-19 — v0.6.0: Skills uplift — gold-standard floor + new deterministic analyzers

A skills-quality release with two tracks, both strictly within the Agent Skills
philosophy (SKILL.md stays concise, detail in references, deterministic helpers
only — no LLM-judgment gates, no hardcoded pricing).

- **Track A — raise the floor (all 13 diagnostic skills now gold-standard):**
  - Added `What Would Falsify This` + `Risks / Open Questions` to every diagnostic
    skill (was 3/13 → now 13/13) — the biggest epistemic gap, curbs over-confident
    diagnosis.
  - Added `> Scope boundary:` notes delimiting each skill from its neighbors to
    reduce routing ambiguity.
  - Standardized the Output Contract across skills: `Route`, `Confidence`,
    `Evidence Quality`, and `Primary Diagnosis: root_cause_type=…, affected_layer=…`
    (was 5 divergent field schemes → one), improving downstream parse + eval match.
  - Fixed references hygiene: deduped `replication.md` (replication-versioning),
    `request-cost.md` (lifecycle-cost), `throttling.md` (performance), and
    `tls-mtu-rtt.md` (network); converted lifecycle-cost refs to the inline
    `| **Read when:**` format; made the access-log parser invocation concrete.
- **Track B — new deterministic diagnostic power:**
  - **event-notification → `notification_target_policy_validator.py`**: checks
    whether a Lambda/SQS/SNS target resource policy actually permits S3 delivery —
    the #1 cause of silently-undelivered events (rule matched, target rejects).
  - **performance → `throttle_tuning_recommender.py`**: turns an observed throttle
    rate + concurrency into concrete safe concurrency / backoff-base / jitter /
    expected-throttle output — upgrades "found throttling" to "here's the fix".
  - **lifecycle-cost → `lifecycle_rule_simulator.py`**: simulates a lifecycle
    config against an object age/size profile and surfaces minimum-duration
    penalties, minimum-billable-size amplification, orphaned-multipart risk, and
    rule conflicts — expressed structurally (days/bytes/multipliers), never money.
- **Eval corpus:** added 3 golden cases with baselines
  (`event-notification-target-policy-missing`, `throttle-tuning-recommendation`,
  `lifecycle-premature-archive-transition`); each new analyzer is unit-tested.

## 2026-06-19 — v0.5.0: Robustness, replication analyzer, eval harness CLI, corpus growth

A consolidated review release: fix long-tail script robustness, give the last
script-less skill a deterministic helper, add a one-command regression harness,
and grow baseline/provider coverage. No new runtime tools or dependencies; the
quality ladder stays deterministic (no LLM-judgment gates).

- **Bug fixes (deterministic, low-risk):**
  - `policy_analyzer.py` now emits the standard `{"ok": false, "error": ...}`
    JSON on an unreadable/missing policy file instead of a Python traceback.
  - `parse_access_log.py` surfaces `parsed_lines` / `skipped_lines` so silently
    dropped malformed log lines are visible to the agent.
  - `parse_sigv4_error.py` reports `xml_parse_fallback` when it degrades from XML
    parsing to the lossy regex path.
  - Corrected the skill-count phrasing across `README`, `ARCHITECTURE`, the
    extension header, and the installer docstring (13 diagnostic + triage +
    reporting + 1 eval = 16 packs).
- **Skills:**
  - **replication-versioning → `replication_status_analyzer.py`**: the last
    diagnostic skill without a helper now has a deterministic offline analyzer
    that classifies the dominant replication/versioning failure (destination
    versioning disabled, rule disabled, delete-marker not replicated, source
    suspended, replication FAILED). Wired into Step 1.
  - **security-iam-policy references**: expanded five stub references
    (policy-evaluation, cross-account, kms-permissions, vpc-endpoints,
    provider-differences) into actionable diagnostic content — the
    highest-traffic 403/AccessDenied domain.
  - **data-consistency** promoted `beta → mature` (tested ETag analyzer + golden
    baseline).
- **Tooling / agent UX:**
  - New `storageops eval` subcommand wraps the golden-case harness:
    `--list`, `--baselines` (score committed baselines), and
    `<case> --output FILE` — the regression workflow in one command, no model
    key required.
- **Eval corpus:**
  - Added baselines for the four previously baseline-less domains
    (access-log, consistency, lifecycle, replication); baseline coverage 17 → 22.
  - New provider-specific case `cos-multipart-etag-corruption` (Tencent COS
    multipart-ETag false "corruption" via a non-native tool) with baseline;
    corpus 36 → 37.
- **Quality gates:** added unit tests for previously-untested gates
  (`no_hardcoded_pricing`, `repo_size_gate`, `version_reference_check`,
  `package_check`) plus the new analyzer and `storageops eval`.

## 2026-06-06 — v0.4.57: Deterministic analyzers for the last two beta skills

Two new offline helpers give the agent diagnostic powers it previously had to
reason out by hand; both keep the quality system deterministic (no LLM-judgment
gates), and raise the two remaining `beta` skills to `mature`.

- **event-notification → `notification_config_analyzer.py`**: parses an S3
  notification configuration and determines deterministically whether a rule
  matches a given object event — covering the skill's top failure class
  (no-config / event-type mismatch, e.g. multipart `CompleteMultipartUpload` vs
  `Put` / prefix-suffix filter mismatch). Wired into Step 1; raises the skill to
  `mature`. New golden case `event-notification-multipart-mismatch`.
- **migration-sync → `sync_log_analyzer.py`**: classifies an rclone/s5cmd/obsutil
  log's dominant error (checksum mismatch vs access-denied vs not-found vs
  throttle), reports transfer counts, and flags a destructive (deleting) sync —
  failure localization the existing cost estimator could not do. Wired into
  Step 6; raises the skill to `mature`. Activates the `migration-metadata-loss`
  golden case with a baseline.
- No new tools/commands/dependencies; deterministic helpers per the quality
  ladder. Eval baseline coverage 15 → 17.

## 2026-06-06 — v0.4.56: Review-response hardening (provider, install, gates, trace docs)

Acts on a third-party audit; each item fact-checked against the code first.

- **Provider detection handles migration/dual-provider**: `detect_domain` now
  returns a `providers[]` array (each with its own confidence/signals/quirks_ref)
  in addition to the primary `provider`, and prompts the agent to apply *each*
  side's quirks for a migration/sync (source vs destination) rather than one
  provider's rules to both.
- **Install mirrors the bundle (no stale skills)**: `storageops install` now
  removes deployed `storageops-*` skills that are no longer in the package
  (renamed/removed), so Pi never loads an out-of-date skill. `doctor` reports
  `unexpected_skills` and warns when stale skills are present.
- **Local/CI gate parity**: new `make validate-full` and `make extension-tests`
  (via `scripts/run_extension_tests.sh`) run the TypeScript extension behavioral
  tests — the routing/provider/trace logic that `make validate` only greps.
  README/AGENTS point contributors at it; `make test` now runs them too.
- **Honest `capture_http_trace` docs**: README/ARCHITECTURE/cli-reference now
  state the three tiers plainly — known read-only allowed, known mutating/
  presigned rejected, and unknown commands run in bounded observation **but are
  still executed**, so a mutating unknown command will perform that mutation.

## 2026-06-06 — v0.4.55: Deterministic provider detection (cross-cutting)

- **Agent is now provider-aware deterministically**: `detect_domain` gains a
  best-effort `provider` (aws/bos/oss/cos/gcs/azure/obs/minio) inferred from the
  endpoint host, vendor header prefixes (`x-bce-`/`x-oss-`/`x-cos-`/`x-goog-`/…),
  vendor CLIs, and URI schemes — even when the user never names the provider.
  Returns `provider_quirks_ref` pointing at that provider's quirks. This attacks
  the #1 object-storage misdiagnosis class: applying AWS assumptions to a non-AWS
  provider. Conservative — returns `unknown` without a clear signal; `x-amz-*`
  is shared by all S3-compatible providers and is *not* treated as an AWS signal.
- **Wired into routing**: triage Step 2 and the provider-quirks "Read when:" gates
  in protocol/bigdata/replication/event now fire when the provider is *detected*
  (endpoint/headers/CLI), not only when the user types its name.
- Framed as **evidence to verify** (endpoints can be proxied/CNAME'd), preserving
  agent judgment. No new tool/command/dependency — one pure `detectProvider()`
  folded into the existing `detect_domain` output.

## 2026-06-06 — v0.4.54: Keep the mount analyzer advisory, not authoritative

- **Preserve agent judgment**: the mount workflow previously said "base the
  recommendation on that verdict" for `mount_workload_analyzer.py`. That
  over-elevated a heuristic (a generic workload→amplification model) to an
  authority. Reworded so the agent treats the analyzer output as *evidence to
  weigh* and reconciles it with the specific mount (e.g. JuiceFS's metadata
  engine or a cache-heavy s3fs config can change the conclusion). Made the run
  conditional on having the inputs, matching the other helper-wirings. Pure
  wording — no code change.

## 2026-06-06 — v0.4.53: Wire deterministic helpers into the agent's workflow

- **Agent now runs the analyzers it has**: several skills shipped deterministic
  helpers but only listed them under *References*, so the agent re-reasoned what
  the tool would have decided. Their workflows now invoke the helper at the
  decision step:
  - bigdata Step 1 runs `analyze_committer.py` for the committer type/risk,
  - mount Step 3 runs `mount_workload_analyzer.py` for amplification/suitability,
  - data-consistency Step 3 runs `etag_parser.py` (previously unmentioned),
  - s3-protocol Step 1 runs `check_payload_hash.py` for `BadDigest` mismatches.
- **Regression guard**: `skill_integrity_check.py` now fails if a
  `scripts/*.py` helper is never named in its `SKILL.md` — a helper the agent's
  instructions never point at is a helper it will never run. Prevents
  "built a helper, forgot to wire it" recurring.
- No new tools, commands, or dependencies — pure capability already built but
  unused, now activated.

## 2026-06-05 — v0.4.52: Consistent, actionable no-key guidance

- **One no-key message everywhere**: a single `_no_key_hint()` is now shown at
  every point a key is missing — install summary, diagnosis launch, and `--help` —
  replacing three divergent texts. It leads with the productized
  `storageops configure --api-key`, then env var and `pi /login`.
- **Diagnosis launch no longer fails silently without a key**: a no-key run like
  `storageops 'diagnose this 403'` now prints the actionable hint before handing
  off to Pi (previously the hint only appeared for the bare interactive launch).
  The check uses the accurate all-provider key source, so a gemini/mistral key in
  the `api-key`/`auth.json` file is no longer mis-reported as missing. It stays
  **non-blocking** — Pi still launches, so `pi /login` is unaffected.

## 2026-06-05 — v0.4.51: Scriptable, machine-readable readiness

- **`storageops doctor --json`**: emits the same readiness report as a
  machine-readable, **redacted** object — it reports the API key *source*, never
  the key value — including `ready` and `next_action`. This collapses what would
  otherwise be a separate "support bundle" command into one flag (no new command,
  no telemetry).
- **`doctor` now has a meaningful exit code**: non-zero when not ready (not
  installed, no API key, or Pi/Node below the minimum), zero when ready — so it
  can gate a script: `storageops doctor && storageops ...`.
- Both modes reuse the existing `_runtime_status()` collector; no new command,
  dependency, or subsystem.

## 2026-06-05 — v0.4.50: Mount analyzer, packaging guard, docs-consistency gate

- **mount/workspace analyzer**: new offline helper
  `storageops-mount-filesystem-workspace/scripts/mount_workload_analyzer.py`
  estimates metadata (HeadObject) amplification, lists the POSIX features a
  workload needs that an object mount cannot provide (atomic rename, locking,
  mmap), flags stale-cache risk, and gives a suitability verdict. Facts mirror
  the skill's POSIX/amplification references.
- **mount/workspace raised `beta` → `mature`**: it now ships a deterministic
  helper, and the existing `workspace-mount-slow-git` golden case gains a passing
  baseline (eval coverage 14 → 15) that cites the analyzer.
- **Packaging guard**: the CI `install-smoke` job now asserts that every
  diagnostic skill pack actually deploys (`>= 15` `storageops-*` under the
  installed skills dir), closing the residual gap between "wheel built" and
  "wheel installs a complete product".
- **Docs-consistency gate**: new `scripts/version_reference_check.py` (wired into
  `make validate`) fails when the version drifts across pyproject, registry,
  ARCHITECTURE, cli-reference, or CHANGELOG. README's golden-case count is no
  longer hardcoded, removing a recurring drift source.

## 2026-06-05 — v0.4.49: Big-data committer depth + Pi version operability

- **bigdata committer analyzer**: new offline helper
  `storageops-bigdata-pipeline/scripts/analyze_committer.py` parses a
  spark-defaults.conf / Hadoop `*-site.xml` / driver log and reports the
  committer type and object-storage risk — FileOutputCommitter v1/v2
  (rename-based, unsafe) vs S3A `magic`/`staging`/`directory`/`partitioned`
  (rename-free). Operationalizes the skill's "identify the committer first" step.
- **bigdata raised `alpha` → `mature`**: it now ships a deterministic helper plus
  a new golden case (`committer-v1-nonatomic`, with a passing baseline) covering
  the non-atomic v1 rename-storm class.
- **Pi version operability**: `doctor` now surfaces when a newer Pi is published
  on npm (`Pi  0.78.0 ... newer Pi 0.78.1 available: npm install -g
  @earendil-works/pi-coding-agent`). Best-effort and silent on failure;
  StorageOps still never auto-upgrades an already-installed Pi.
- **Maturity honesty**: `mount-filesystem-workspace` corrected `mature` → `beta`
  (it has no deterministic helper, which the ladder defines `mature` as having).

## 2026-06-05 — v0.4.48: Routing and secret-scan regression hardening

- **Negative routing corpus**: added deterministic false-positive cases for
  bare-substring traps such as ordinary `sync`, ticket `transfer`, `mountain`,
  `version`, `event`, `uncertain`, `jobs:`, `blobs:`, and `archive`.
- **Strong-signal ranking contract**: golden routing tests now require selected
  high-confidence cases to rank their expected skill first, while preserving the
  documented top-2/top-3 allowance for genuinely multi-signal cases.
- **Narrower ambiguous signatures**: migration `sync`/`transfer` now require
  storage or migration context, and mount detection no longer matches ordinary
  words such as `mountain`.
- **Secret-scan evidence contract**: tests now lock in that credential material
  is redacted while canonical request labels, hosts, payload hashes, request IDs,
  and ETags remain available for diagnosis.

## 2026-06-04 — v0.4.47: Routing & scan correctness, measured by the corpus

- **Golden corpus now gates routing**: a new deterministic test feeds every
  golden-case input through `detect_domain` and asserts the expected skill is
  recalled (top-2, with one documented multi-signal case at top-3). Previously
  the `routing-*` cases were never executed against the routing engine. Baseline
  measured: recall@any 34/34, @top-2 33/34.
- **Protocol error-code recall**: `detect_domain` now routes
  `RequestTimeTooSkewed`, `RequestExpired`, `NotImplemented`,
  `MissingContentLength`, `EntityTooLarge`, `EntityTooSmall`, and
  `PreconditionFailed` to s3-protocol-compatibility (previously unmatched).
- **`RequestExpired` no longer leaks to lifecycle**: the lifecycle `expir`
  signature is word-bounded (`\bexpir(...)\b`), so the protocol error code stops
  scoring lifecycle while real "expiration"/"expired" language still routes.
- **scan_secrets closes a SigV4 leak**: the `Signature=<hex>` in an
  `Authorization: AWS4-HMAC-SHA256` header is now redacted, while the credential
  scope (date/region/service) and payload hashes stay visible as diagnostic
  evidence.
- **`etag_parser` accepts BOS ETags**: a BOS multipart ETag (`-<32hex>`, leading
  dash) can now be passed as a positional argument instead of being rejected by
  argument parsing as an unknown option.

## 2026-06-04 — v0.4.46: Close the over-broad routing-signature class

- **Fix the class, not the case**: after fixing `bos:` (v0.4.44) and `obs:`
  (v0.4.45) one at a time, `detect_domain` still carried bare-substring
  signatures that misrouted ordinary text at medium confidence. Tightened the
  clear offenders:
  - `version` → `\bversioning\b|version id` (so "rclone version 1.65" no longer
    routes to replication-versioning),
  - `event` → `event notification|bucket event|SQS|Lambda` (so "in the event of"
    no longer routes to event-notification),
  - `cert` → `\bcert(?:ificate)?\b` (so "uncertain" no longer routes to TLS).
  Genuinely ambiguous migration words (`transfer`/`sync`) are intentionally left
  for multi-signal disambiguation rather than over-tightened.
- **Regression guard**: a new `detect_domain` test feeds benign/cross-domain
  noise and asserts it does not produce these misroutes, while confirming real
  versioning/event/TLS evidence still routes correctly — so the next
  bare-substring signature is caught automatically.

## 2026-06-04 — v0.4.45: Routing precision & readiness consolidation

- **`obs:` no longer over-matches**: `detect_domain`'s obsutil signature is now
  `\bobsutil\b|\bobs:\/\/` so ordinary words like `jobs:`/`blobs:` no longer
  misroute to the CLI/SDK obsutil subdomain, while real `obs://` URIs still
  route. This finishes the word-boundary pass started for `bcecmd` in v0.4.44.
- **`configure` schema pinned**: confirmed against Pi 0.78 `core/settings-manager`
  that Pi reads `defaultProvider`/`defaultModel` from `{agentDir}/settings.json`
  (its `globalSettingsPath`) — the exact file/keys `storageops configure` writes.
  Documented the invariant in code so future Pi drift is caught.
- **Readiness consolidation (no behavior drift)**: `--version` and `doctor` now
  share one `_runtime_status()` collector, and `doctor`'s skill check compares
  deployed packs against the count actually bundled in the wheel instead of a
  hardcoded threshold.

## 2026-06-04 — v0.4.44: BOS BadDigest routing fix

- **Protocol routing recall**: `detect_domain` now recognizes `BadDigest`,
  `BadDigestSHA256`, `BadDigestMD5`, and BOS `x-bce-content-sha256` evidence as
  S3/BOS protocol compatibility signals.
- **Less false routing**: Big-data engine signatures now use word boundaries, so
  ordinary words such as `archive` no longer trigger the `Hive` route.
- **BOS client precision**: `bos:` URIs and `bcebos` backend mentions no longer
  masquerade as `bcecmd`; only explicit `bcecmd`/`go-bcecli` evidence selects
  the bcecmd client subdomain.

## 2026-06-04 — v0.4.43: First-run readiness commands

- **`storageops doctor`**: added a concise readiness report covering package/PyPI
  version, Node, Pi, install mode, skill count, `httpmon`, API key source,
  default provider/model, and common key-source conflicts.
- **`storageops configure`**: added a small configuration command for default
  provider/model and local `api-key` setup without hand-editing JSON.
- **`storageops smoke`**: added an explicit, opt-in model smoke test. It performs
  one minimal Pi model call and never touches object storage.
- **Better `--version` signal**: now includes package path, deployed version,
  latest PyPI, and default provider/model for easier support screenshots.

## 2026-06-04 — v0.4.42: User documentation accuracy pass

- **Corrected user-facing facts**: README now reflects the current 34 golden
  cases and includes the payload-hash helper in the deterministic script list.
- **Clearer write-side guidance**: README, tutorial, and quick reference now
  point users to failed-request evidence and `check_payload_hash.py` for
  `BadDigest`/payload-hash cases without suggesting that writes should be traced.

## 2026-06-04 — v0.4.41: Write-side evidence ladder (no live write tracing)

- **Doctrine, not loosening**: `capture_http_trace` executes commands, so tracing
  a write performs a real mutation — its read-only posture is unchanged. Instead,
  write-side failures (failing PUT/copy, `BadDigest`, `SignatureDoesNotMatch`) are
  diagnosed from the request's evidence: read the server error body, read the
  client's own debug dump (`aws --debug` / `rclone -vv --dump headers` / boto3
  `set_stream_logger`), then recompute offline. Documented once in
  `storageops-s3-protocol-compatibility/references/checksum-etag.md` and pointed
  to from the protocol/cli-sdk skills and the shared quality guide (no duplicated
  per-tool flag tables — the per-tool references already carry them).
- **`BadDigest` is not corruption**: new reference section and decision-tree
  branch identify `x-amz-content-sha256` mismatch as a SigV4 payload-hash bug
  (commonly: hash computed over uncompressed bytes while a gzip body is sent).
  The misleading "bit flip" nudge is corrected to distinguish deterministic
  request-construction failures from intermittent transport corruption.
- **Optional offline falsifier**: `scripts/check_payload_hash.py` confirms or
  refutes the payload-hash-over-wrong-bytes mechanism offline (no creds, no
  network, no signing). Positioned as an optional confirmation step, not a gate.
- **Rejection becomes a redirect**: a rejected write trace now returns a
  `guidance` field pointing at the evidence ladder (pay-per-use; no permanent
  context cost). Read-only trace autonomy is explicitly unchanged.

## 2026-06-04 — v0.4.40: Evidence-first diagnosis discipline

- **Shared evidence-first contract**: `docs/skill-quality-guide.md` adds an
  "Evidence-First Discipline" section binding every skill to three rules —
  evidence overrides priors, confidence is bounded by what was examined, and
  falsify before concluding. This targets the systemic failure mode where a
  diagnosis pattern-matches an error string instead of inspecting the decisive
  artifact in front of it.
- **Confidence hard caps**: `storageops-triage/references/confidence-rubric.md`
  adds caps that override the scoring table and adjustment factors — an
  uninspected decisive artifact caps confidence at 0.50, resemblance/memory is
  not evidence, and a diagnosis with no named falsifier cannot be presented as
  High. A worked "resemblance trap" example seeds the discipline.
- **Flagship adversarial golden case**: `resemblance-gzip-baddigest` reproduces a
  real misdiagnosis class — a `BadDigest` that looks like data corruption but is
  actually a client computing `x-amz-content-sha256` over uncompressed bytes
  while sending a gzip-compressed body. A diagnosis that reads only the error
  string HARD_FAILs; one that inspects the script passes. Measured by the
  existing eval/CI, no new subsystem.

## 2026-06-04 — v0.4.39: Soft observation for unclassified trace commands

- **Less tool-policy overreach**: `capture_http_trace` no longer rejects custom
  SDK probes merely because an argument value looks like `delete`, `copy`, or
  `sync`. Unknown clients now reject explicit HTTP write methods, then use
  bounded metadata observation plus warnings for suspicious arguments.
- **Known clients degrade gracefully**: storage clients such as `rclone`, `mc`,
  and `s5cmd` still reject clear mutating operation positions, but unclassified
  non-mutating commands fall back to observation instead of requiring an ever
  growing allowlist.
- **Agent-readable guardrails**: trace results now include
  `operation_unclassified=true` when the command is observed without a dedicated
  operation classification. Body capture, shell/sudo wrappers, presigned URL
  material, raw HAR/record output, and replay remain unavailable.

## 2026-06-04 — v0.4.38: Host mismatch as trace warning

- **Less premature rejection**: `capture_http_trace` no longer rejects curl or
  unknown-client observation solely because a command URL host differs from
  `filter_host`. Real object-storage paths often involve global endpoints,
  region endpoints, CNAMEs, CDN fronts, gateways, or SDK endpoint indirection.
- **Still visible to the agent**: host mismatch now returns
  `host_mismatch=true` plus a warning that the trace may capture zero requests,
  so the agent can adjust `filter_host` instead of losing the chance to observe
  the run.
- **Safety boundaries unchanged**: shell/sudo wrappers, presigned URL material,
  body capture, HAR/record/replay, obvious mutating unknown-client arguments,
  and curl non-read-only methods/body upload flags are still rejected.

## 2026-06-04 — v0.4.37: Unknown-client HTTP trace observation

- **Unknown clients are no longer rejected solely by executable name.**
  `capture_http_trace` now allows tightly bounded observation for custom SDK
  probes and vendor CLIs that StorageOps does not have a dedicated adapter for,
  such as small `python`/`node` diagnostics or tools like `ossutil`/`coscli`.
- **Safety stays narrow**: unknown-client observation still requires
  `filter_host`, rejects shell/sudo wrappers, rejects presigned URL material,
  rejects obvious mutating arguments (`put`, `delete`, `upload`, `sync`, etc.),
  enforces URL host matching when URLs are present, keeps `capture_body=false`,
  and is capped at 5 requests / 15 seconds.
- **Trace output now labels the policy** with
  `client_policy=known_adapter|unknown_observation` and marks
  `method_violation=true` if captured metadata shows a non-read-only HTTP
  method.

## 2026-06-04 — v0.4.36: Flexible capture_http_trace validation

- **Less brittle read-only tracing**: `capture_http_trace` now validates by the
  command's operation position instead of scanning every argv value for words
  like `delete`, `sync`, or `copy`. Read-only requests for objects or prefixes
  with those names are no longer rejected before they can emit HTTP evidence.
- **More complete read-only AWS coverage**: added common metadata/listing
  operations needed for WORM, event-notification, logging, ownership, policy,
  and versioning diagnosis (`get-object-retention`, `get-object-legal-hold`,
  `get-bucket-notification-configuration`, `list-object-versions`, and related
  bucket metadata calls).
- **Safer curl parsing**: `curl -XPOST`, `curl --request=POST`, and other
  method forms are now rejected correctly, and curl URL hosts must match
  `filter_host`. The tool still rejects body capture, shell/sudo wrappers,
  mutating operations, raw HAR/record, replay, and presigned URL material by
  default.

## 2026-06-03 — v0.4.35: capture_http_trace response headers + behavioral tool tests

- **`capture_http_trace` now returns sanitized response headers.** A real WORM
  diagnosis showed the decisive evidence (`x-bce-object-rentention-date`) lived in
  a response header the tool dropped, forcing an unsafe raw-`curl` fallback. The
  tool now surfaces response metadata with **targeted** sanitization: cookie/auth
  header values are masked (name kept), redirect targets (`location`) are stripped
  of presigned signatures, and all other headers (ETag, retention, SSE, checksums)
  pass through unmodified — no blanket redaction that would corrupt the evidence.
  Request headers remain shape-only; no body/HAR/replay.
- **Behavioral unit tests for the 4 tools.** The TypeScript tool layer previously
  had only static-assertion coverage (which is why the v0.4.29 recall bug shipped).
  Added `node:test` tests that exercise the real `redactText`, `detectDomain`,
  `searchTokens`, `searchMemory`, `validateTraceCommand`, and
  `sanitizeResponseHeaders`, run in a new `tool-tests` CI job (the extension's
  `typebox` import is satisfied by a one-line CI-time stub; no new dependency, no
  installer change, single-file extension preserved).

## 2026-06-03 — v0.4.34: Node pre-flight + documentation cleanup

- **Node pre-flight check**: `storageops install` now verifies Node before
  installing Pi. If Node `< 22.19.0` it stops with an actionable message
  ("upgrade Node, then re-run") instead of npm-installing the incompatible legacy
  Pi (0.74.2) that StorageOps then rejects with a confusing "not ready". The
  "pi too old" path likewise points at Node when Node is the real blocker.
- **`--version` shows a `node` line** alongside the existing readiness fields.
- **Documentation review/cleanup** (clear stale info, fill gaps, improve clarity):
  - `SECURITY.md`: corrected the tool count (3 → 4) and the `scan_secrets`
    coverage list (presigned-URL material, GCP, Azure); noted the plaintext
    `api-key` file surface and `chmod 600`.
  - `CONTRIBUTING.md`: added `capture_http_trace` to the extension tool list;
    noted commands run from the repo root.
  - Documented the `provider:key` api-key prefix (previously only in the
    CHANGELOG) in README, getting-started, and cli-reference.
  - Fixed the example docs: non-canonical `checksum_etag` category →
    `consistency_integrity`, and removed the stale `severity` field (dropped from
    the golden-case schema in v0.4.27).
  - Fixed eval examples that referenced an undefined `diagnoses/` directory;
    clarified the maturity-level table (`core` is orthogonal).
- Removed the worked-example block from the README.

## 2026-06-03 — v0.4.33: Honest key-status reporting

- **Fixed misleading "API key not configured"**: the install summary (and now
  `--version`) reported key presence using environment variables only, while the
  launcher actually authenticates from environment **+ the `api-key` file +
  `auth.json`**. On the install/version path the injector never runs, so a
  file-configured key (which works for diagnosis) was reported as missing. A
  single `_configured_key_source()` now checks the same three sources the
  launcher uses, across all seven supported providers.
- **`--version` now shows an `api key` readiness line** (env / api-key file /
  auth.json), making it the honest one-glance status view. It reports presence,
  not validity.
- Found via real-host validation on a configured cloud instance.

## 2026-06-03 — v0.4.32: Tool reliability & effectiveness

- **`scan_secrets` — presigned-URL material**: now redacts presigned signature/
  credential params (`X-Amz-Signature`/`X-Amz-Credential`/`X-Amz-Security-Token`,
  `X-Goog-Signature`, OSS `Signature`/`OSSAccessKeyId`, COS `q-signature`/`q-ak`).
  These appear constantly in rclone/aws/s5cmd debug logs and were passing through
  un-redacted.
- **`scan_secrets` — multi-cloud keys**: added GCP service-account keys (PKCS8
  `PRIVATE KEY` + `private_key_id`) and Azure (`AccountKey=`, SAS `sig=`).
- **`search_memory` — dedupe per session**: a session matching in both its
  summary and JSONL no longer occupies two result slots, improving recall
  diversity.
- **`detect_domain` — CJK parity**: added Chinese signatures to the core domains
  that lacked them (security, performance, network, cli/sdk, s3-protocol), so
  Chinese inputs route correctly.
- All changes are additive and stay inside the single-file extension (no new
  tools, files, dependencies, or installer/CI changes); each was verified with
  positive + negative samples and locked with static-assertion tests.

## 2026-06-03 — v0.4.31: ETag provider-fact verification

- **Verified the multipart ETag facts across providers** against vendor sources
  and corrected/hedged them. **COS**: removed an unsupported, likely-fabricated
  claim ("MD5 of first part's MD5 + last part's MD5") — no Tencent doc supports
  it. **OSS**: kept the verified fact (multipart ETag differs from S3 and is not
  the object MD5) but marked the specific algorithm unverified rather than
  asserting "MD5 of part ETags". **MinIO**: confirmed AWS-compatible `<hex>-N`.
  **S3/BOS**: unchanged (S3 trailing `-N`; BOS leading `-`, fixed in v0.4.30).
- **Canonical ETag matrix**: `checksum-etag.md` is now the single source of truth
  (provider × shape × computation × verification status); `data-consistency`'s
  `etag-format.md` links to it instead of restating, to prevent drift.
- **Parser**: documented that multipart classification is by string *shape*
  (S3/MinIO/OSS/COS all share `<hex>-N`; the per-provider computation lives in the
  matrix, not the parser) and added a test locking shape-based classification.
- Each corrected provider fact carries an inline source + date; unverifiable
  specifics are explicitly marked unverified rather than guessed. (No CI
  provenance gate — regression is locked by content-level tests, not doc ceremony.)

## 2026-06-03 — v0.4.30: Provider-fact correctness & tool gaps

- **BOS vs S3 multipart ETag**: corrected a wrong cross-provider fact. The data-
  consistency parser classified an invented `crct…-md5` "composite" BOS ETag, and
  the BOS quirks reference claimed BOS uses S3's trailing `-N` suffix. Reality:
  BOS multipart ETags are the md5 of concatenated part md5s with a **leading `-`**
  and **no part count** (`-<32 hex>`), versus S3's **trailing** `<32 hex>-N`.
  `etag_parser.py`, `bos.md`, and `checksum-etag.md` now agree on this.
- **Intelligent-Tiering**: `small_object_analyzer.py` no longer flags IT objects
  under 128 KB as a min-billable "penalty" — IT has no per-object minimum size
  charge (set to 0).
- **Access-log BOS/COS**: the parser now refuses to emit silently-zeroed records
  when its (unverified) BOS/COS column mapping doesn't match the input headers,
  and the contradictory `provider-log-formats.md` is marked unverified. The real
  formats still need confirmation against vendor docs.
- **search_memory CJK**: Chinese queries previously tokenized to nothing and
  recalled zero results; the tokenizer now emits CJK bigrams.
- **capture_http_trace allowlist**: added the read-only S3 ops the CORS /
  lifecycle / multipart / tagging skills depend on (`head-bucket`,
  `get-bucket-cors`, `get-bucket-lifecycle-configuration`, `get-bucket-tagging`,
  `get-bucket-acl`, `get-object-attributes`, `list-multipart-uploads`).
- **Honesty**: relabeled `storageops-migration-sync` `mature → beta` (its
  references are stub-level). Added Python static-assertion tests locking the
  extension fixes (CJK tokens, allowlist, recursive session recall).

## 2026-06-02 — v0.4.29: Memory recall & provider-explicit keys

- **`search_memory` recall fix**: the tool only scanned the top level of the
  sessions directory, so it missed transcripts Pi stores under scope
  subdirectories (e.g. `sessions/<scope>/<id>.jsonl`) — recall was effectively
  empty under real Pi layouts. It now walks the sessions tree with bounded
  depth/count, indexes by `.jsonl` (so sessions are found even without a
  `.meta.json`), and treats `.meta.json` as optional sibling enrichment. Flat
  top-level layouts still work.
- **api-key file is provider-explicit**: the plain `api-key` file assigned the
  key to the first unset of DeepSeek/Anthropic/OpenAI, silently misrouting any
  non-DeepSeek key (Anthropic, Gemini, Groq, etc.) to `DEEPSEEK_API_KEY`. It now
  honors an optional `provider:key` prefix (e.g. `anthropic:sk-ant-...`) routed
  via the provider map — matching Pi's provider-explicit auth model. A bare key
  keeps the DeepSeek-first default for backward compatibility.
- **Cleanup**: removed the unimplemented `--json` flag from `repo_size_gate.py`.

## 2026-06-02 — v0.4.28: Adversarial baselines & helper test coverage

- **Adversarial safety baselines**: added committed baseline outputs for all four
  adversarial golden cases (delete-bucket, make-public, disable-tls,
  credential-exposure). These now positively lock the v0.4.27 safety gate — they
  prove a correct safe diagnosis passes while the forbidden phrasing stays out —
  raising baseline eval coverage from 8 to 12 cases.
- **Golden-case fix**: `adversarial-make-public` listed the literal `Principal":
  "*"` in both `must_include_evidence_keywords` and `must_not_include`, which is
  unsatisfiable (no output can both contain and omit it). Removed it from
  `must_not_include`; recommending public access is still blocked by the
  remaining natural-language patterns, and citing the wildcard in analysis is
  allowed per the unsafe-output rules.
- **Helper test coverage**: added unit tests for the previously untested
  `parse_access_log` (largest, most heuristic helper), `etag_parser`,
  `small_object_analyzer`, and `regression_reporter`.
- **Routing clarity**: documented the 429/SlowDown scope boundary between
  `storageops-performance-diagnosis` (owns throttling) and
  `storageops-cli-sdk-diagnosis` (tool-version-specific 429 only).

## 2026-06-02 — v0.4.27: Correctness & safety-gate hardening

- **Eval safety gate**: `eval_runner` no longer lets a negation cue in a separate
  clause suppress a forbidden-output hit (e.g. "Do not hesitate. Delete the
  bucket."). A negation now only suppresses a hit when it governs the keyword in
  the same clause, closing a bypass in the `must_not_include` safety check.
- **Test suite green**: removed an unnecessary `from __future__ import
  annotations` that made `endpoint_reachability_test.py` fail to import under the
  test harness; the full suite now passes.
- **Helper script fixes**: `migration_cost_estimator` returns a structured error
  instead of crashing on `bandwidth_mbps`/`overhead_factor` of 0;
  `throttle_detector` no longer double-counts a line that carries both a status
  code and a keyword; `parse_access_log` exits non-zero on empty input; and
  `etag_parser` reports unreadable files through its JSON error contract.
- **Release gate**: the publish workflow now runs `skill_integrity_check.py` and
  `pytest` before building, so a red suite cannot reach PyPI.
- **Schema & docs**: removed the unused, inconsistently-named `severity` field
  from golden cases; `golden_case_validator` now enforces the shape of
  `expected_root_cause_types` when present; `package_check` derives the expected
  skill count from the source tree; corrected the skill count in the README, the
  golden-case field names in the eval skill, and a duplicated reference entry.

## 2026-06-02 — v0.4.26: Inline tool hardening

- **Secret scanning**: `scan_secrets` now redacts only the sensitive value when
  possible, preserves surrounding context, returns line/column metadata, and
  fingerprints only the secret value. Large inputs and outputs are bounded.
- **Domain routing**: `detect_domain` now returns matched evidence signals,
  `recommended_skill`, ambiguity status, and a compact next-action hint so the
  agent can choose a skill without over-routing.
- **Memory search**: `search_memory` now tokenizes queries, scores summary and
  JSONL matches, caps scanned sessions, and redacts snippets before returning
  prior-session context.

## 2026-06-02 — v0.4.25: Bundled httpmon helper

- **No preinstalled httpmon required on Linux amd64**: release builds now
  package a verified, gzip-compressed Linux amd64 `httpmon` helper inside the
  StorageOps wheel/sdist. During `storageops install`, StorageOps copies a
  matching bundled helper into `~/.storageops/bin/httpmon` before trying any
  network download.
- **Packaging gate**: `scripts/package_check.py` now prepares and verifies the
  bundled helper assets in both wheel and sdist artifacts, so PyPI releases
  cannot silently omit the helper.
- **Repository and package size control**: helper binaries are generated during
  packaging and ignored by Git. v0.4.25 bundles the cloud-default Linux amd64
  helper while other supported platforms keep the bounded download fallback.

## 2026-06-02 — v0.4.24: Bounded httpmon download

- **Install robustness**: automatic httpmon helper downloads now use a bounded
  `curl --max-time 20` path when curl is available, falling back to a short
  urllib timeout otherwise. Slow GitHub release downloads warn and continue
  instead of hanging `storageops install`.

## 2026-06-02 — v0.4.23: Managed httpmon bootstrap

- **Managed helper install**: `storageops install` now prepares a verified
  `httpmon` release binary in `~/.storageops/bin/httpmon` when the platform is
  supported, so `capture_http_trace` does not require users to install httpmon
  manually.
- **Runtime discovery**: StorageOps prepends `~/.storageops/bin` to `PATH` before
  launching Pi, and the extension also checks the managed helper path directly
  for merged Pi installs.
- **Safety**: downloads are SHA-256 verified and failures are warnings, not
  blockers for normal log-based diagnosis.

## 2026-06-02 — v0.4.22: PyPI README tool metadata

- **README metadata**: updated the package README to show all four Pi extension
  tools, including `capture_http_trace`, so PyPI project metadata matches the
  installed v0.4.21 tool surface.

## 2026-06-02 — v0.4.21: Bounded HTTP trace capture

- **Agentic evidence capture**: added `capture_http_trace`, a narrow Pi tool
  that can run one read-only object-storage command through `httpmon` and return
  a sanitized HTTP summary.
- **Safety boundaries**: the wrapper rejects shell commands, presigned URL
  material, body capture, mutating object-storage operations, raw HAR/record
  output, and replay.
- **Skill integration**: protocol, network, CLI/SDK, and performance skills can
  use sanitized HTTP evidence when headers, status, redirects, or signing shape
  would materially improve diagnosis.
- **Tests/Docs**: added static guard tests and documented the limited tool
  surface in architecture and CLI references.

## 2026-06-02 — v0.4.20: Install version guardrails

- **Install transparency**: `storageops install` now prints the local package
  version, package path, and deploy target before copying files, so stale local
  packages are visible during upgrades.
- **Best-effort PyPI warning**: the installer warns when PyPI has a newer
  StorageOps release but the local package is older, without blocking offline
  or restricted environments.
- **Deployment provenance**: installs now write `~/.storageops/install.json`
  with package version, package path, target agent, skills path, mode, and time.
- **Docs**: updated install and upgrade guidance to keep the main flow simple
  while documenting Ubuntu/Debian `externally-managed-environment` handling.

## 2026-06-02 — v0.4.19: Reference scope guardrails

- **BOS CMD correction**: fixed `bcecmd` configuration guidance to use the BOS
  CMD default `~/.go-bcecli/` directory or an explicit `conf-path`, and clarified
  that BCE SDKs have separate configuration patterns.
- **Reference scope gate**: added `scripts/reference_scope_check.py` so CLI/SDK
  references must state their scope and verification steps before tool-specific
  paths, defaults, or config facts are applied.
- **Known false-fact denylist**: added a guard against the old `~/.bce/*`
  bcecmd path claims returning in any skill reference.
- **Tests/CI**: added regression tests for the new reference gate and wired it
  into `make validate` and GitHub Actions.

## 2026-06-02 — v0.4.18: Safety and verifiability patch

- **Secret scanning safety**: `scan_secrets` findings now return only line,
  type, length, and a short SHA-256 fingerprint instead of raw secret previews.
- **Pricing fact hygiene**: moved volatile cost assumptions out of runtime
  `SKILL.md` instructions into dated references and added a hardcoded-pricing
  validation gate.
- **Eval hardening**: `eval_runner.py` now enforces
  `expected_root_cause_types`, and baseline outputs include explicit root-cause
  type fields where needed.
- **Skill contracts**: documented a lightweight modern output contract with
  validation steps and falsifiability, then applied it to security, performance,
  and CLI/SDK diagnosis skills.

## 2026-06-02 — v0.4.17: Publish on main merge

- **Main-merge publishing**: `publish.yml` now runs on every `main` push as well
  as `v*` tags, so release PR merges can publish to PyPI automatically.
- **Duplicate protection**: the workflow checks PyPI for the current
  `pyproject.toml` version and skips publishing when that version already exists,
  preventing same-version documentation or maintenance merges from failing.
- **Docs**: updated release guidance to make version bump + PR merge the primary
  release path, with tags retained as an optional compatibility trigger.

## 2026-06-02 — v0.4.16: PyPI release automation hardening

- **Publish workflow**: split PyPI publishing into build/preflight and publish
  jobs so the exact checked artifacts are uploaded on every matching `v*` tag.
- **Release validation**: added `twine check`, package asset verification, artifact
  upload/download, concurrency control, and explicit read/OIDC permissions.
- **Preflight**: added manual `workflow_dispatch` validation for release plumbing
  changes without publishing to PyPI.
- **Docs**: added a release guide documenting the one-time PyPI Trusted Publisher
  setup and the tag-based release flow.

## 2026-06-02 — v0.4.15: Low-version Pi install guard

- **Install guard**: `storageops install` now stops before deploying files when an
  existing Pi Coding Agent is below `0.78.0`, avoiding half-ready installs where
  StorageOps files are present but Pi cannot load the required agent directory or
  Extension API contract.
- **Tests/docs**: added installer regression coverage for the low-version Pi path
  and updated user-facing install guidance plus version metadata.

## 2026-06-02 — v0.4.14: PyPI publishing, Pi auto-install, install verification

- **PyPI publishing**: added `.github/workflows/publish.yml` with PyPI Trusted Publisher
  (OIDC) so releases are published automatically on `v*` tags. A pre-publish job
  verifies that the tag version matches `pyproject.toml` to prevent version drift.
- **Pi auto-install**: `storageops install` now detects whether Pi Coding Agent is
  present and installs it via `npm install -g @earendil-works/pi-coding-agent`
  automatically when it is absent. If npm is not available the command exits with
  a clear error and a link to nodejs.org. When Pi is present but below the minimum
  version, the installer prints the upgrade command rather than auto-upgrading,
  to avoid disrupting existing Pi configurations.
- **Install verification**: replaced the previous unconditional "installation complete"
  message with a structured post-install summary that reports the status of each
  component (StorageOps files, Pi Coding Agent, API key) and exits non-zero only
  when the tool cannot run at all (Pi missing or below the supported version). A
  missing API key is reported as a warning with configuration instructions, not a
  hard failure.
- **No-emoji CLI output**: removed all emoji from CLI print statements in
  `storageops_cli/__init__.py` for compatibility with terminals and log pipelines
  that do not handle Unicode correctly.
- **Docs**: updated README Quick Start with the explicit Pi install step, an
  Ubuntu/Debian pip note, and the corrected skill count (16). Updated
  `docs/getting-started.md` Prerequisites to list Node.js as a requirement and
  document the auto-install behavior.
- **Skill count**: corrected "15 diagnostic skills" to "16 diagnostic skills" in
  README (the eval skill pack was always present in code but the prose was inconsistent).

## 2026-06-02 — v0.4.13: Eval matcher hardening

- **Eval matcher**: added structured `Category`, `Route`, and `Confidence` field parsing before fallback text matching.
- **Keyword matching**: replaced naive substring checks with deterministic token/literal matching for short tokens, symbolic keywords, and CJK text.
- **Safety eval**: refined forbidden-output checks to ignore explicit safe-negation contexts such as "do not delete bucket" while still catching unsafe recommendations.
- **Tests/docs**: added matcher regression coverage and documented compact structured baseline-output expectations.

## 2026-06-02 — v0.4.12: Routing contract alignment

- **Routing contract**: extended `docs/skill-taxonomy.json` with signatures and baseline eligibility so categories, skills, aliases, and eval coverage share one contract.
- **Validation**: added `scripts/routing_contract_check.py` and CI coverage for taxonomy, registry, golden cases, baseline outputs, and deterministic domain signatures.
- **Baseline coverage**: added compact outputs for big-data small-file and event-notification prefix-filter cases, bringing baseline eval to 8 cases.
- **Docs**: updated taxonomy and quality guidance for maintaining routing contract alignment.

## 2026-06-02 — v0.4.11: Baseline eval and package quality gates

- **Eval baseline**: added compact baseline outputs for six high-value golden cases and an `eval_all.py --only-with-outputs` mode for subset scoring.
- **Size gates**: added `scripts/repo_size_gate.py` to reject generated artifacts, oversized fixtures, oversized golden cases, and baseline corpus growth.
- **Package check**: added `scripts/package_check.py` and CI coverage for wheel/sdist skill assets, extension presence, and Python cache exclusion.
- **CI/docs**: wired baseline eval, repo size gates, and package checks into CI and contributor documentation.

## 2026-06-02 — v0.4.10: Review bug fixes and real CI gates

- **CI**: GitHub Actions now installs dev dependencies, runs skill integrity checks, validates golden cases, and runs pytest.
- **Security tooling**: fixed public-policy detection for list/dict principal forms, broad resources, `NotAction`, and `NotPrincipal`; explicit Deny statements are now informational.
- **Credential loading**: fixed standard AWS credentials parsing for `key=value` profile files.
- **Routing/eval**: aligned deterministic domain detection with skill names, added protocol/big-data/CORS signatures, improved confidence scoring, and made eval enforce confidence thresholds.
- **Packaging/docs**: excluded Python cache files from source distributions and clarified skill counts, examples, changelog, and credential-loader security posture.

## 2026-06-02 — v0.4.9: Merge install settings preservation

- **Merge install fix**: `storageops install --merge` now preserves existing Pi `skills` paths and appends StorageOps' `../skills` path once instead of replacing the whole list.
- **Tests**: added CLI installer coverage for skill-path merging and settings preservation.
- **Version sync**: bumped the package and registry header to v0.4.9 for the installer bugfix release.

## 2026-06-02 — v0.4.8: Documentation rewrite and review notes

- **Documentation rewrite**: refreshed README, operator guides, contributor/security notes, architecture docs, CLI reference, quick reference, tutorial, skill quality guide, taxonomy/routing docs, dependency map, API matrix, and rclone examples.
- **Review visibility**: documented the packaging-data contract where root-level skills are exposed through `storageops_cli/skills -> ../skills` and must remain aligned with installer lookup paths.
- **Version sync**: bumped the package and registry header to v0.4.8 for the documentation-only release.

## 2026-06-02 — v0.4.7: Output contracts and size gates

- **Output contracts**: softened all skill output sections from rigid exact templates to required-field contracts.
- **Size gates**: added integrity-check budgets for SKILL.md files, taxonomy JSON, golden-case inputs, individual cases, and total golden-case corpus size.
- **Documentation**: updated skill quality and taxonomy docs with enforced repository size budgets.

## 2026-06-02 — v0.4.6: Endpoint reachability checker

- **Network tooling**: added `endpoint_reachability_test.py` for read-only DNS, TCP, TLS, and HTTP HEAD checks against an explicitly provided endpoint.
- **Layer classification**: reports the first failing layer as DNS, TCP, TLS, HTTP, application, or reachable.
- **Skill integration**: wired the checker into `storageops-network-endpoint-access` guidance and documented authorized-use constraints.
- **Tests**: added offline unit coverage for endpoint parsing, failure classification, and application-level HTTP status handling.

## 2026-06-02 — v0.4.5: SigV4 evidence parser

- **Protocol tooling**: added `parse_sigv4_error.py` to extract SigV4 error code, StringToSign, CanonicalRequest, credential scope, signed headers, and likely inspection points from XML/debug logs.
- **Skill integration**: wired the parser into `storageops-s3-protocol-compatibility` guidance and replaced the placeholder script note with concrete usage.
- **Tests**: added parser coverage for service XML responses and client debug blocks.

## 2026-06-02 — v0.4.4: Specialist diagnosis case coverage

- **Coverage**: added compact diagnosis golden cases for access-log delete storms, multipart ETag verification, big-data small-file queries, notification prefix filters, and migration metadata loss.
- **Regression suite**: expanded golden cases from 28 to 33 while keeping inputs small and synthetic.
- **Documentation**: updated eval examples and version references for the expanded suite.

## 2026-06-02 — v0.4.3: Batch golden-case evaluation

- **Batch eval**: added `eval_all.py` to evaluate saved outputs across many golden cases and emit regression-ready JSON summaries.
- **Eval summaries**: added PASS/SOFT_FAIL/HARD_FAIL/MISSING counts, pass rate, and per-category aggregation for saved-output suites.
- **Tests**: added coverage for batch eval summaries, missing outputs, and taxonomy-mapped skill scoring.
- **Documentation**: updated eval and skill quality docs with batch evaluation and regression baseline commands.

## 2026-06-02 — v0.4.2: Skill taxonomy and routing quality gates

- **Taxonomy contract**: added `docs/skill-taxonomy.json` and `docs/skill-taxonomy.md` to map golden-case categories to primary skills.
- **Routing coverage**: added 8 compact routing golden cases for ambiguous 403/signature, mount/performance, CORS, Spark committer, access-log, notification, migration, and stale-read scenarios.
- **Validation**: upgraded skill integrity and golden-case validators to reject unknown `expected_category` values.
- **Eval scoring**: `eval_runner.py` now accepts either the canonical category or the mapped skill name in diagnostic output.
- **Documentation**: updated skill quality and eval docs for taxonomy-backed golden cases and repository size budgets.

## 2026-06-01 — Skill quality gates and reference integrity

- **Reference integrity**: aligned SKILL.md bundled-resource links with real files and added missing domain references for big data, consistency, event notification, and migration skills.
- **Metadata consistency**: synchronized `skill-registry.yaml` maturity/mode values with SKILL.md frontmatter and moved the registry contract marker to v4.
- **Quality gates**: added `scripts/skill_integrity_check.py` and wired `make validate` to verify skill metadata, references, tools, registry paths, and golden-case schemas.
- **Eval automation**: implemented deterministic golden-case validator, unsafe-output scanner, single-case eval runner, and regression reporter.
- **Documentation**: added `docs/skill-quality-guide.md` to define skill structure, validation commands, golden-case requirements, and maturity rules.

## 2026-06-01 — Review fixes: merge skills path, memory search, skill registry sync

- **Merge install fix**: copy skills to the directory referenced by each target agent's `../skills` setting, so `storageops install --merge` uses `~/.pi/skills`.
- **Session memory fix**: `search_memory` now resolves sessions from `PI_CODING_AGENT_DIR` before falling back to `~/.pi/agent`.
- **Skill registry sync**: added `storageops-access-log-analysis` to registry and routing docs; updated skill-pack counts from 15 to 16.
- **Robustness**: pi version detection now extracts semver from prefixed version output; auth env injection accepts provider keys that do not start with `sk-`.

## 2026-06-01 — Smart install, PI_CODING_AGENT_DIR fix, api-key persistence

- **PI_CODING_AGENT_DIR fix**: Pi 0.78.0 uses `PI_CODING_AGENT_DIR` to resolve agent config, not `PI_HOME`. Directory restructured to `~/.storageops/agent/`.
- **API key persistence**: Added `~/.storageops/agent/api-key` plain-text file support. `_inject_auth_env()` reads it before launching Pi — completely shell-independent, works regardless of `.bashrc`/`.profile` sourcing.
- **Smart install detection**: `storageops install` detects existing Pi config (`~/.pi/`) and offers interactive choice: isolated (`~/.storageops/`) or merged (`~/.pi/`).
- **Pi version guard**: Warns if pi < 0.78.0 (Extension API requirement).
- **Extension moved**: `storageops_cli/extensions/storageops.ts` — removed from `.pi/extensions/` to avoid Pi auto-discovery conflicts.
- **Improved install guidance**: Three API key configuration methods shown at install completion.

## v0.4.0 — 2026-06-01: Lightweight Pi Extension Redesign

**Zero Python agent code** — the entire 48-file Python agent package has been deleted.
StorageOps is now a pure Pi Coding Agent extension + skill pack.

### Removed
- **storageops/** Python package (48 files) — all agent loop, session management,
  tool dispatch, CLI, REPL, API server, MCP server, config, audit, diagnostics
- **parsers/**, **analyzers/**, **utils/** directories — 21 files deleted.
  LLM reads raw logs directly; no pre-parsing needed.
- **tool_bridge.py** + `spawnSync` — tools now run inline in TypeScript extension
- **docs/review/** — 7 old review documents removed

### Added
- **`.pi/extensions/storageops.ts`** — rewritten as standalone TypeScript extension
  with 3 inline tools: `scan_secrets`, `detect_domain`, `search_memory`
- **`storageops_cli.py`** — thin CLI shim that forwards to `pi`

### Changed
- **skills/** moved to root (was `agents/skills/`)
- **All SKILL.md files** updated — `recommended_tools` reduced to 3 tools
- **README, AGENTS.md, docs/** — completely rewritten for new architecture
- **pyproject.toml** — slimmed to optional thin CLI, no heavy deps

### Architecture
- **Agent loop**: Pi Coding Agent (was custom agent.py)
- **Session**: Pi session manager (was custom session.py)
- **Tools**: Pi Extension API (was tool_bridge.py + if-elif dispatch)
- **Diagnostic logic**: SKILL.md instructions (was parsers/analyzers)
- **UI**: Pi TUI (was custom display.py + repl.py)

## v0.3.0 — 2026-06-01: Complete architecture rebuild

**Unified package** — merged `storageops-cli` + `storageops-core` into single `storageops` package.
No more sys.path hacks or dual-package coordination.

**Append-only session** — JSONL event log + meta.json sidecar.
Session is NEVER read-then-rewritten. Resume works correctly on every turn.

**Stateless agent** — `converse(session, input, display)`. No class, no modes, no global state.
Model decides when to use tools vs chat.

**Flat architecture** — `core/`, `ui/`, `cli/`, `runtime/` directories deleted.
All modules at package root. Import depth ≤ 2.

**Pi events as raw JSON** — zero translation layer. Pi upgrades require zero changes.

**Net**: ~4500 lines deleted, ~2000 new, -56% code, -60% directories.

---

## 2026-06-01 — Architecture refactor: natural conversational agent

**Core: prompt -> identity, no mode switching**
- Rewrote `pi_diagnosis_prompt.md` from 2500+-token diagnostic manual to ~500-token
  natural identity prompt. No mode switching — the model decides whether to chat,
  diagnose, or use tools based on context.
- Removed `pi_chat_prompt.md` — one prompt for all modes.
- Removed `_is_chat_message()` keyword detection and all chat/diagnose branching.

**Core: PiSession — persistent Pi process across turns**
- New `PiSession` class in `runtime/pi_rpc.py`: maintains one Pi subprocess across
  multiple turns. Conversation history is preserved — the model remembers previous
  interactions without needing to rebuild context.
- `PiRpcRuntime` kept for one-shot CLI commands (`triage`, `analyze`, `eval`).
- First turn: sends full system prompt + evidence file path.
  Subsequent turns: sends just the user message. Pi retains context.

**Core: non-blocking safety lint**
- `validate_agent_report()` → `safety_lint()`: scans for secrets and dangerous
  recommendations but NEVER blocks output. Safety notes appended as gentle reminders.
- YAML frontmatter validation removed from the agent pipeline (still available
  for eval/tests via `validate_report()`).

**REPL: simplified streaming display**
- `_StreamDisplay` simplified from 5-state dispatch (thinking/tool/YAML/report/chat)
  to 2 phases: thinking → response. No more YAML-collecting logic or mode-dependent
  formatting. All model output streams naturally.
- `_run_turn()` uses persistent `_pi_session` singleton; restarts on `/clear` or
  `/resume`.

## 2026-06-01 — Amp-style slash commands + command history + syntax highlighting

- **`/editor` command**: open `$EDITOR` (vim/nano) to write long prompts or paste large logs.
  Comment lines (`#`) are stripped; save-and-exit sends the prompt to Pi.
- **Shell mode (`$ cmd`)**: run shell commands inline; stdout (first 200 chars) is captured
  and added to session evidence for context-aware diagnosis.
- **Fuzzy `@file` matching**: glob patterns (`@*.log`, `@/tmp/my-log*`) and prefix matching
  (`@s5cmd` → most recent `s5cmd*` file by mtime). Absolute paths supported.
- **`/view` command**: opens the last assistant report in `less -R` pager for full-screen
  browsing; falls back to first 50 lines if less is unavailable. Applies pygments syntax
  highlighting when installed (YAML/JSON/bash/code blocks).
- **`/history` command**: shows last N interactive commands (`/history <N>`); defaults to 20.
  Readline history persists to `~/.storageops/history` with `↑`/`↓` and `Ctrl+R` search.
- **Progress timestamps**: elapsed seconds shown on each tool call result during streaming.
- **Streaming fix**: `_StreamDisplay` event handlers updated for actual Pi JSONL format
  (`tool_execution_start`/`tool_execution_end` replacing `tool_use`/`tool_result`;
  `text_start` supplementing `text_delta`).
- **`cli.py` fix**: removed stale `_LiveProgress` reference → `_StreamDisplay`.

## 2026-06-01 — Pi Extension + RPC protocol fix

- **Pi Extension** (`.pi/extensions/storageops.ts`): all 21 StorageOps diagnostic tools are
  now registered natively in Pi via `pi.registerTool()`. Pi's LLM can call them directly during
  multi-turn diagnosis sessions without any MCP or text-based tool list.
- **`runtime/tool_bridge.py`**: lightweight Python bridge subprocess. Reads `{tool, inputs}` from
  stdin, calls `dispatch_tool()`, writes JSON result to stdout. Called by the TypeScript Extension.
- **RPC protocol fix** (`runtime/pi_rpc.py`):
  - Request type corrected from `"diagnose"` (unsupported) to `"prompt"` (real Pi command)
  - Model configuration sent via `set_model` command before `prompt`
  - `stdin` kept open during the session (previously closed immediately, blocking all tool calls)
  - Terminal event updated from `final_report` to `agent_end` (real Pi protocol)
  - Report extracted from `agent_end.messages[].content[].text`
  - Streaming via `message_update.assistantMessageEvent.text_delta`
  - Fixed `ValueError: I/O operation on closed file` when draining stderr after `stdin.close()`
- **`pi_diagnosis_prompt.md`**: removed hand-written tool list (tools now registered natively);
  updated evidence collection strategy to call tools directly.
- **Tests**: fake Pi helper updated to emit real Pi RPC events (`agent_start`,
  `message_update/text_delta`, `agent_end/messages`). 109/109 tests pass.
- **Architecture docs** (`ARCHITECTURE.md`, `CLAUDE.md`, `README.md`, `docs/cli-reference.md`):
  updated to reflect Pi Extension as the correct tool registration path.

## 2026-05-31 — Pi Coding Agent-style REPL rewrite

- **`repl.py` complete rewrite**: interactive session now matches Pi Coding Agent / Ampcode UX
- **Single-Enter submit**: removed double-Enter (empty-line) submission model; press Enter once to send. Paste detection via `select` collects multi-line clipboard content as one message.
- **Minimal banner**: `StorageOps  anthropic  ·  type / for commands  ·  Ctrl+C to interrupt  ·  /exit to quit`
- **Session ID on startup**: `  Session  a3f2b1c8` shown immediately after banner (like Pi/Ampcode)
- **Removed UX noise**: domain classification (`Domain: security_iam_policy 91%`), evidence block counts, `has_log_content` gate, and `_first_turn` hint hack are all gone — the interface is a clean conversation
- **Tool call display**: verbose mode shows `⏺ tool_name · result_summary` per tool invocation
- **New `/status` command**: shows session ID, turn count, Pi status, API key status, verbose toggle
- **Code reduction**: 758 lines → 340 lines (−55%)
- **Docs**: README, cli-reference, getting-started, ARCHITECTURE, CHANGELOG updated to reflect new UX

## 2026-05-31 — httpmon integration + full documentation rewrite

- **httpmon integration**: `parse_httpmon_log` parser captures wire-level S3 signals from
  httpmon NDJSON (`--format json`) and HAR (`--har`) output. Auth header values are classified
  (sigv4/presigned/anonymous) but never exposed.
- **MCP tool**: `parse_httpmon_log` registered in `tool_registry.py`; available to Pi and
  Claude Desktop via MCP.
- **Skills v2 recommended tool calls**: `parse_httpmon_log` added to `storageops-performance-diagnosis`
  and `storageops-network-endpoint-access` recommended tool tables.
- **README**: httpmon installation, three usage patterns, and "what httpmon reveals" comparison table.
- **Docs overhaul**: `CHANGELOG.md`, `docs/cli-reference.md`, `docs/getting-started.md`,
  `CONTRIBUTING.md`, `ARCHITECTURE.md`, `storageops-cli/README.md`, `storageops-core/README.md`,
  and `docs/tutorial.md` all rewritten to reflect current CLI commands, install flow, and architecture.

## 2026-05-25 — Modern CLI commands + Skills v2 contract

- **Session persistence**: REPL sessions auto-saved to `~/.storageops/sessions/`; each session has
  a unique ID and timestamp. Evidence blocks and conversation turns are preserved across restarts.
- **`storageops resume`**: list recent sessions or resume a specific session by ID.
- **`storageops config list/get/set`**: manage `~/.storageops/config.json` from the CLI;
  API key stored under `api_key`, provider under `provider`.
- **`storageops update`**: re-downloads Pi binary and reinstalls skills without a full reinstall.
- **`storageops scan`**: renamed from `batch`; `batch` retained as a hidden alias.
- **Hidden aliases**: `agent` → `diagnose`; `batch` → `scan`; `analyse` → `analyze`.
- **Skills v2 contract**: all 15 skills upgraded with structured frontmatter (`maturity`, `mode`,
  `estimated_tokens`, `trigger_keywords`, `recommended_tools`), Output Envelope v2
  (`confidence_factors`, `evidence_quality_score`, `next_actions`), Recommended Tool Calls table,
  Light/Heavy dual mode, and Thinking framework blockquote.
- **`skill-registry.yaml` v2.0**: updated to reflect v2 contract, maturity levels, and all 15 skills.
- **`storageops-data-consistency`**: expanded from 64-line stub to a full skill with complete
  diagnosis workflow, root cause pattern library, and output requirements.
- **README**: fully rewritten for human beginners and AI agents; includes REPL demo, session
  resume, slash commands, httpmon table, MCP tool table, Output Envelope v2 example, skills table
  with maturity column.

## 2026-05-17 — Interactive REPL + Pi auto-install + API key config

- **REPL (`storageops`)**: natural-language interactive session with multi-turn evidence accumulation.
- **`@file` references**: `> analyze this log @/var/log/s3-error.log` inlines file content.
- **Slash commands**: `/help`, `/clear`, `/doctor`, `/setup`, `/verbose`, `/exit`.
- **`storageops setup`**: guided wizard that installs Pi, selects LLM provider, and stores API key.
- **Pi auto-install**: `storageops setup` downloads Pi binary automatically; `storageops doctor`
  checks environment health and reports Pi status.
- **One-shot pipe**: `aws s3 cp s3://bucket/key . 2>&1 | storageops`.
- **README**: hero demo, 2-command install, provider table.

## 2026-05-10 — pip install + setup/doctor

- **pip-installable**: `pip install storageops` (PyPI); no git clone required.
- **`storageops setup`** and **`storageops doctor`** added as primary user-facing commands.
- Config stored at `~/.storageops/config.json`.
- **`storageops triage`** and **`storageops analyze`** work offline without Pi or an API key.
- **`storageops diagnose`**: sends redacted evidence to Pi and returns a validated markdown report.

## 2026-04-28 — Offline engine, Makefile, network parser

- `parse_network_diagnostics.py` — parses `dig`/`curl -v`/`ping` output.
- `analyze_network.py` — DNS/TLS/TCP/VPC endpoint root cause from parsed diagnostics.
- Makefile targets: `make test`, `make lint`, `make eval`.
- SKILL.md files translated to English; v1 skill structure.
- All tests run without LLM, Pi, or network access.

## v0.1.0 — Skill Pack

- **10 diagnostic skills**: triage, S3 protocol, CLI/SDK, performance, mount, network, security,
  lifecycle, reporting, eval.
- **47 reference documents** covering SigV4, ETag, multipart, rclone, s5cmd, IAM policy, KMS,
  lifecycle, and more.
- **4 report templates**: customer, engineering note, reproduction checklist, diagnosis report.
- **5 golden cases** with `expected.json` validation schemas.
- **AGENTS.md + README.md** — project-level agent instructions.
- **`skill-registry.yaml`** — skill discovery and routing.
