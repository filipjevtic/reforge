# Changelog

All notable changes to reforge are recorded here. This project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Decision-grade reporting: `resolved_rate` now carries a Wilson 95% confidence
  interval, `pass@k` is reported when `--repeats > 1`, `report --compare` prints a
  cost/quality Pareto table (mean $/task, dominated vs on-frontier) and a
  two-proportion significance note for the top two models. Existing `report.json`
  files gain these on re-render, no re-run needed.

### Security
- Git sources reject transport helpers (`ext::`, `fd::`) and option-like
  repo/ref values.
- Provider API keys / bearer tokens are redacted from persisted task error text.
- Agent adapters pass the model via an environment variable instead of
  interpolating it into the shell command.
- Task containers set a `nofile` ulimit and trace files are capped so a chatty
  agent cannot fill the host disk.

## [0.3.0] - 2026-07-26

### Security
- Verification now runs in a fresh container from the task image with only the
  agent's captured diff replayed onto clean source, so a reward-hacking agent can
  no longer shim the test runner, drop a `sitecustomize.py`, or pre-write the
  report to forge a passing result.
- Judge prompt hardened against injection from the agent's diff (the diff is
  labeled untrusted data the judge must not follow).
- `source.subdir` is rejected if it escapes the source root.

### Removed
- Dead code: unused `Settings`/`get_settings` (drops the `pydantic-settings`
  dependency), the reserved no-op `verify-gold --keep-container` flag, and other
  unreferenced helpers/fields.

### Fixed
- Test-id matching no longer credits a bare `test_add` to a qualified
  `pkg.mod::test_add`, and the `.py` strip is extension-anchored.
- Dependency coverage no longer counts substring matches (`s3` in
  `aws_s3_bucket`, or a name in a comment); the `grep` detector tokenizes on word
  boundaries.
- The pass_to_pass regression gate fails closed when no tests result exists.
- Client-side timeouts are no longer retried (they may already be billed).
- The API agent returns an error to the model on a malformed tool call instead of
  failing the whole task; the diff-capture step raises on git failure instead of
  writing a garbage patch.

## [0.2.0] - 2026-07-26

### Added
- Free-form task `category` plus `tags`, with `run --category`/`--tag` filters.
- Pluggable scorers (`reforge.scorers`) and detectors (`reforge.detectors`) via
  entry points; `scoring.weights` is now keyed by scorer name.
- New built-in detectors: `k8s_refs`, `js_imports`, `go_imports`, `package_manifests`.
- Project config via `reforge.toml` / `[tool.reforge]`; `run --fail-under` exit
  code for CI adoption gating. `reforge list scorers`.
- Credentialed tasks: `run --env-passthrough KEY` forwards a host env var into a
  task only if the task allowlists it in `environment.allowed_env`.
- `reforge init` task scaffolder, and two cookbook samples:
  `cloud-infra-terraform` and `devops-k8s`.

## [0.1.1] - 2026-07-24

### Added
- HuggingFace dataset loading: `--dataset hf:owner/repo[@revision]`.
- Podman support via `--runtime podman` (uses Podman's Docker-compatible socket).
- Best-effort `disk_quota` enforcement, with a graceful fallback when the storage
  driver doesn't support it.
- Cross-run comparison: `reforge report --compare`.
- `--repeats` for per-task score variance and `--max-cost-usd` to cap spend.
- Retry with backoff for transient provider errors in the LLM client.
- Key-gated live smoke test for the real provider SDK path (agent + judge).

### Changed
- A failing adapter or scorer now fails only its task, never the whole run.

### Fixed
- Files copied into a task container are normalized to root ownership, so runs
  work on hosts (like CI runners) where the checkout is owned by a non-root user.

## [0.1.0] - 2026-07-24

First alpha. The core harness and hybrid scoring, end to end:

- Containerized task lifecycle: build, isolate, snapshot, run the agent, capture
  the diff before tests are injected, verify, score.
- Hybrid scoring: deterministic tests (FAIL_TO_PASS / PASS_TO_PASS), a
  dependency-coverage scorer that names what the agent missed, and an LLM judge.
- Two task categories: replication and new-feature, with a unified schema.
- BYO-agent adapters (`noop`, `gold`, `command`, `api-agent`, `claude-code`,
  `aider`) discovered through entry points.
- CLI: `init`-free authoring via examples, `validate`, `verify-gold`, `run`,
  `report`, `schema`, `list`, `adapter-check`.
- Docker-based, self-hosted, Apache 2.0.
