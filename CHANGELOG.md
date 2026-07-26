# Changelog

All notable changes to reforge are recorded here. This project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Free-form task `category` plus `tags`, with `run --category`/`--tag` filters.
- Pluggable scorers (`reforge.scorers`) and detectors (`reforge.detectors`) via
  entry points; `scoring.weights` is now keyed by scorer name.
- New built-in detectors: `k8s_refs`, `js_imports`, `go_imports`, `package_manifests`.
- Project config via `reforge.toml` / `[tool.reforge]`; `run --fail-under` exit
  code for CI adoption gating. `reforge list scorers`.

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
