# Contributing to reforge

Thanks for taking the time to help. This guide covers how to get set up, what the
checks expect, and how to propose changes.

## Getting set up

You need Python 3.11 or newer and Docker.

```bash
git clone https://github.com/filipjevtic/reforge
cd reforge
make install          # pip install -e ".[dev]"
pre-commit install    # optional, runs ruff on commit
```

## Before you push

Run the same checks CI does:

```bash
make check            # ruff + mypy + unit tests
make test-docker      # the Docker integration tests (gold self-verify, noop guard)
```

The Docker tests build a small image and run real containers, so they need a
working Docker daemon. If you can't run them locally, say so in your PR and CI
will run them for you.

## How the pieces fit together

- `spec/` parses and validates a task.
- `runtime/` builds images and runs containers.
- `adapters/` drive an agent inside a container.
- `runner/` ties a single task's lifecycle together and orchestrates a dataset.
- `scoring/` turns a finished run into a score.
- `report/` aggregates and renders results.

[docs/architecture.md](docs/architecture.md) walks through it in more depth.

## Adding a task

The fastest way to learn the format is to copy `tests/fixtures/tiny-task` and
adjust it. A task is only valid once its gold solution resolves it:

```bash
reforge validate path/to/your-task
reforge verify-gold path/to/your-task
```

Both must pass before you open a PR that adds a task. See
[docs/task-authoring.md](docs/task-authoring.md).

## Adding an adapter

An adapter is a class that drives one agent. Implement `AgentAdapter`, register it
under the `reforge.adapters` entry-point group, and it shows up in
`reforge list adapters`. See [docs/adapter-authoring.md](docs/adapter-authoring.md).

## Commits and pull requests

- Keep commits focused. Conventional-commit prefixes (`feat:`, `fix:`, `docs:`,
  `chore:`, `refactor:`, `test:`) are appreciated but not enforced.
- Branch off `main`; open a PR against `main`. Direct pushes to `main` are blocked.
- Fill in the PR template. Link the issue you're closing.

## Reporting bugs and asking questions

Use the issue templates for bugs and features. For open-ended questions, start a
[Discussion](https://github.com/filipjevtic/reforge/discussions). For security
problems, follow [SECURITY.md](SECURITY.md) instead of filing a public issue.
