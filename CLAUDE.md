# reforge: notes for Claude

A CLI that benchmarks how well AI coding agents replicate and extend a codebase.
Python, src-layout, package `reforge`, CLI `reforge`. Apache 2.0.

## Running checks

Run everything in Docker. Do not rely on a host Python; on this machine the
homebrew Python's `pyexpat` is broken, so `venv`/`pip`/`ruff`/`pytest` fail
natively. The pattern:

```bash
docker run --rm -v "$PWD":/repo -w /repo -v reforge-pip-cache:/root/.cache/pip \
  python:3.12-slim bash -c "pip install -q -e '.[dev]' && \
  ruff check src tests && ruff format --check src tests && mypy && pytest -m 'not docker' -q"
```

The Docker-marked integration tests build images and run containers, so add
`-v /var/run/docker.sock:/var/run/docker.sock` and run `pytest -m docker`. Some
integration tests need `git` in the base image; the sample-task images install it.

`make check` and `make test-docker` wrap these once a working Python exists.

## Layout

- `spec/` parse + validate a task (`task.yaml`).
- `workspace/` resolve source (git/local/tarball) and prep a clean copy.
- `runtime/` build images, run containers, exec, copy (docker-py; `factory.py`
  selects docker vs podman).
- `adapters/` drive one agent in a container; discovered via the
  `reforge.adapters` entry-point group.
- `scoring/` tests + dependency-coverage + judge, composed with a regression gate.
- `runner/` per-task lifecycle and dataset orchestration.
- `report/` aggregation and rendering.
- `llm/` provider-agnostic client (Anthropic + OpenAI-compatible), cost, retry.

## Conventions

- `main` is protected: work on a feature branch, open a PR, let CI pass (Lint,
  Unit 3.11/3.12/3.13, Docker integration), then `gh pr merge <n> --squash
  --admin --delete-branch` (solo maintainer).
- ruff is pinned (0.16.0) so local and CI never skew. Run `ruff format` before
  committing.
- Keep human-facing text em-dash-free (the repo uses the humanizer skill).
- A task is only valid if its gold solution resolves it: `reforge verify-gold
  <task>`. CI checks this for every task under `tasks/`.
- Adapters and scorers must never crash the run: a failure becomes a task-level
  error. Keep it that way.
