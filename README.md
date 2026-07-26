# reforge

**Benchmark how well AI coding agents work on _your_ codebase, not someone else's.**

Public leaderboards tell you how a model does on public repositories. They can't
tell you the thing you actually need to know before you adopt a tool: how well
does this agent do the work _we_ do, in _our_ code? reforge answers that. You give
it tasks built from your own repositories, point it at any agent (a frontier CLI,
a hosted API, an open-weights model), and it reports back with reproducible,
comparable scores.

It measures two kinds of work that map onto how teams actually adopt AI:

- **Replication**: reproduce something that already exists, using the codebase as
  context. "Stand up staging and test environments that mirror prod." Did the
  agent wire up every service and config dependency, or quietly drop Redis?
- **New features**: build something that isn't there yet, with little prior
  context. "Add an analytics dashboard over our events table." Does it work, and
  does it fit how the rest of the code is written?

reforge is a command-line tool. There is no UI, no SaaS, nothing to sign up for.
It runs on your machine, against your Docker daemon, and your code never leaves it.

## How it works

reforge borrows the parts of [SWE-bench](https://www.swebench.com/) and
[Terminal-bench](https://www.tbench.ai/) that have proven out, and adds what those
benchmarks don't cover for this problem.

A **task** is a directory: a `task.yaml`, a `Dockerfile` for the environment, a
verifier that runs the tests, and a gold (reference) solution. For each task
reforge:

1. builds the task image and copies your code into a fresh, network-isolated
   container;
2. snapshots a base commit, then hands the container to an **adapter** that drives
   the agent under test;
3. captures the agent's diff with git, *before* the held-out tests are ever
   injected, so nothing can be gamed;
4. runs the verifier and scores the result.

Scoring is a blend rather than a single pass/fail:

- **Tests**: the SWE-bench bar. The tests that should now pass do, and nothing
  that used to pass broke.
- **Dependency coverage**: did the agent wire up every dependency the task says a
  correct solution needs? Misses are listed by name.
- **LLM judge**: a rubric score for the fuzzier questions of accuracy and style.

You choose the weights per task, and you can turn the judge off entirely for a
fully deterministic run.

## Install

reforge needs Docker and Python 3.11+.

```bash
pip install -e ".[dev]"        # from a clone
```

## Quick start

```bash
# Check a task is well-formed.
reforge validate tests/fixtures/tiny-task

# Prove the task's gold solution actually resolves it (no LLM involved).
reforge verify-gold tests/fixtures/tiny-task

# Run an agent against a single task. `gold` applies the reference solution,
# so the task resolves; `noop` changes nothing, so it doesn't.
reforge run --task tests/fixtures/tiny-task --adapter gold --format table

# Point --dataset at a directory of tasks to run them all and print a leaderboard.
reforge run --dataset ./tasks --adapter gold --format table
```

Results land in `runs/<run-id>/`: a `report.json`, and per task the captured
diff, the verifier log, and a `result.json` with the full score breakdown and
provenance.

## Comparing agents and models

The whole point is to compare. Run each candidate, then put them on one board:

```bash
reforge run --dataset ./tasks --adapter api-agent --model claude-sonnet-4-6 --run-id claude
reforge run --dataset ./tasks --adapter api-agent --model gpt-4.1 --run-id gpt
reforge report runs/claude --compare runs/gpt
```

The comparison groups by adapter and model and shows resolved rate, mean score,
dependency coverage, and total cost side by side.

Two more controls matter when the models cost money and sometimes flake:

- `--repeats N` runs each task N times and reports the score variance, so a lucky
  pass doesn't look like a reliable one.
- `--max-cost-usd N` stops launching tasks once the run's spend reaches your
  budget, so a large dataset against a frontier model can't run away with the bill.
- `--resume` reuses the same `--run-id` and skips tasks already scored, so a long run
  that stops partway (a flaky container, a rate limit, the budget) picks up where it
  left off instead of starting over. Tasks that errored are retried.

### Reading the numbers

The report is built to defend an adoption decision, not just rank models:

- **Resolved rate comes with a 95% confidence interval** (Wilson score), shown as
  `67% [39%-86%]`. With a handful of tasks the interval is wide on purpose: a
  four-point lead that sits inside both intervals is noise, not a winner.
- **`pass@k`** appears when you use `--repeats`. `pass@1` is the single-shot rate;
  `pass@k` is the chance at least one of `k` attempts succeeds, using the unbiased
  estimator from the HumanEval paper. A big gap between `pass@1` and `pass@k` means
  the agent can do the task but isn't reliable.
- **Cost vs quality** ranks models by mean dollars per task and flags which ones are
  on the Pareto frontier. A model that is both pricier and worse than another is
  marked *dominated*: never the right buy.
- A **significance note** under a `--compare` board reports whether the leader's
  resolved rate beats the runner-up (two-proportion test). Treat it as a large-sample
  guide; the confidence intervals are the more reliable read when task counts are low.

## Project config and CI gating

Put run defaults in a `reforge.toml` (or a `[tool.reforge]` table in
`pyproject.toml`) so runs aren't flag-soup. Flags override the file; the file
overrides built-in defaults:

```toml
# reforge.toml
adapter = "api-agent"
model = "claude-sonnet-4-6"
judge_model = "claude-sonnet-4-6"
concurrency = 4
fail_under = 0.8
```

`reforge run --fail-under 0.8` exits non-zero (code 2) if the resolved rate is
below the threshold, so you can wire reforge into CI as an adoption gate: does
this model clear our bar on our own tasks?

## Datasets and runtimes

`--dataset` takes a local directory or a HuggingFace dataset repo of reforge task
directories:

```bash
reforge run --dataset hf:acme/reforge-tasks --adapter gold        # or hf:acme/tasks@v1
```

That pulls the repo with `huggingface_hub` (install `reforge[hf]`) and runs it like
any local dataset. Row-based HF datasets aren't supported; the convention is a
git-backed dataset repo whose files are task directories.

reforge runs on Docker by default and on Podman with `--runtime podman`. Podman
exposes a Docker-compatible API socket, so this is the same tested code path
pointed at Podman's socket; set `DOCKER_HOST` to override where it looks.

## Writing a task

A task directory looks like this:

```
my-task/
├── task.yaml            # the spec: prompt, tests, scoring weights, limits
├── Dockerfile           # the environment
├── verifier/
│   └── run_tests.sh     # runs the tests, writes JUnit XML to $REFORGE_REPORT
├── gold/
│   └── solution.patch   # the reference solution
└── (your source, or a git ref in task.yaml)
```

`reforge init <id> --category <domain>` scaffolds this layout for you.
`tests/fixtures/tiny-task` is a complete, minimal example, and `tasks/` holds a
starter cookbook (analytics, staging env, Terraform, Kubernetes). See
[docs/task-authoring.md](docs/task-authoring.md) for the full schema.

## Bringing your own agent

An adapter is a small class that drives one agent inside the container. The ones
that ship today:

- `noop` and `gold`: no LLM, used to test the harness itself.
- `api-agent`: a minimal tool-loop agent over any model reachable through the
  Anthropic API or an OpenAI-compatible endpoint (OpenAI, Gemini, Kimi, and so
  on). This is how you compare a frontier model against a non-frontier one on the
  same scaffold.
- `claude-code` and `aider`: thin wrappers around those CLIs running inside the
  task container.
- `command`: run any shell command as the agent. The task instruction and model
  are passed in as environment variables, so you can wire up a tool that has no
  Python adapter at all.

Adapters are discovered through Python entry points, so a third-party adapter is
just a package you `pip install`. `reforge new-adapter <name>` scaffolds that package
for you; `reforge list adapters` shows what's installed, and
`reforge adapter-check --adapter <name>` preflights its credentials. See
[docs/adapter-authoring.md](docs/adapter-authoring.md).

Pick the model with `--model`, and pass adapter-specific options as JSON with
`--config`, for example:

```bash
reforge run --task tests/fixtures/tiny-task --adapter api-agent --model claude-sonnet-4-6
reforge run --task my-task --adapter command \
  --config '{"command": "my-agent --model $REFORGE_MODEL \"$REFORGE_INSTRUCTION\""}'
```

## A note on safety

reforge runs code produced by an agent. Each task runs in its own container with
no network by default, dropped capabilities, and CPU, memory, and PID limits. A task
that needs the network for only a few hosts can set `environment.allowed_hosts`, and
reforge confines it to a filtering proxy that blocks everything else. Even so, treat
agent output as untrusted and run reforge on a disposable or isolated host. It never
mounts your Docker socket into a task container.

## Known limitations

This is alpha software. Worth knowing before you rely on it:

- Reported costs are estimates from a small built-in pricing table that can go
  stale. Verify against current provider pricing for anything that matters.
- Model versions aren't pinnable the way source commits are. reforge records the
  model id in each result, but providers can change a model behind that id.
- The LLM judge is run at temperature 0 and can be sampled with a median, but it
  is not perfectly reproducible. For a fully deterministic run, use `--no-judge`.
- `api-agent` is a deliberately minimal scaffold, not a state-of-the-art agent.
  It exists so any model works out of the box on the same footing; for a specific
  agent, write an adapter.
- Supported on Linux and macOS with Docker (or Podman). Windows is untested.

## Status

Early and moving fast. The task format and adapter contract are stabilizing; see
the [open issues](https://github.com/filipjevtic/reforge/issues) and
[docs/architecture.md](docs/architecture.md) for where things are headed.

## License

Apache 2.0. See [LICENSE](LICENSE).
