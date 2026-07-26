# Writing a task

A task is a directory. reforge reads `task.yaml` and expects a Dockerfile, a
verifier, and a gold solution next to it. The quickest way to start is to copy
`tests/fixtures/tiny-task` and change it.

```
my-task/
├── task.yaml            # the spec
├── Dockerfile           # the environment
├── src/                 # your code (for a local source), or use a git ref
├── verifier/
│   ├── run_tests.sh     # runs the tests, writes JUnit XML to $REFORGE_REPORT
│   └── tests/           # held-out tests, injected only after the agent runs
└── gold/
    └── solution.patch   # the reference solution
```

## The two categories

Every task declares a free-form `category` and optional `tags`. `category` is any
label you like; common ones are:

- **`replication`**: reproduce something that already exists in the codebase.
  These lean on `dependency_coverage`. You list the services, config keys, and
  imports a correct solution must wire up, and reforge reports what the agent
  missed.
- **`new_feature`**: build something new. These lean on `fail_to_pass` tests and
  the judge rubric.

Nothing stops you from using `cloud-infra`, `devops`, `ai-dev`, or your own label,
since the domain is really defined by your Dockerfile, verifier, and detectors.
`tags` are cross-cutting labels (`[terraform, aws]`); `reforge run --category X`
and `--tag Y` filter a dataset down to a subset.

The schema is the same for every category. What differs is which blocks you fill in.

## Minimal task.yaml

```yaml
schema_version: 1
id: my-task
category: new_feature
title: "Implement the thing"
instruction: |
  Plain-English description of what the agent should do.

source:
  type: local        # local | git | tarball
  path: src          # for local; use repo + ref (a SHA) for git
  strip_git: true

environment:
  dockerfile: Dockerfile
  workdir: /workspace

verification:
  entrypoint: verifier/run_tests.sh
  framework: pytest
  fail_to_pass:
    - "test_thing.py::test_it_works"
  pass_to_pass:
    - "test_thing.py::test_unrelated_still_works"

scoring:
  weights: { tests: 1.0, dependency_coverage: 0.0, judge: 0.0 }
```

The full field list is in [the JSON Schema](task.schema.json), which you can
regenerate with `reforge schema --output docs/task.schema.json`.

## The verifier contract

`verifier/run_tests.sh` runs after the agent's diff has been captured, in a fresh
container built from the task image with that diff replayed onto a clean copy of the
source (so nothing the agent left behind in its own container can affect grading).
It must:

1. Run the test framework against the workspace (which now has the agent's changes).
2. Write a JUnit XML report to the path in `$REFORGE_REPORT`.

The tiny task's script is a good template:

```sh
#!/bin/sh
set -e
cd /verifier/tests
PYTHONPATH=/workspace pytest test_calc.py \
  --junitxml="${REFORGE_REPORT:-/tmp/reforge_report.xml}" -o junit_family=xunit2
```

Test ids in `fail_to_pass` / `pass_to_pass` are matched against the report across
rootdir and directory-prefix drift, so `test_calc.py::test_add` matches whether or
not the runner reports the `.py` or a leading path. A qualified id still has to
agree on both the module and the test name, so a same-named test in a different
module never matches by accident; a bare `test_add` matches only when exactly one
test in the report carries that name.

## Dependency coverage (replication tasks)

List the ground-truth dependencies and how to detect what the agent actually used:

```yaml
dependency_coverage:
  required:
    services: ["postgres", "redis"]
    config_refs: ["DATABASE_URL", "REDIS_URL"]
    imports: []
  detectors:
    - type: env_refs
      scope: "environments/staging/**"
```

reforge reports the coverage ratio and, more usefully, the exact list of what was
missed.

## The gold solution

`gold/solution.patch` is a unified diff (as produced by `git diff`) that solves the
task. It exists so reforge can prove the task is well-formed:

```bash
reforge verify-gold my-task
```

If the gold solution doesn't resolve the task, the task is broken. Fix it before
using it to grade anyone. CI runs this on every shipped task.

## Resource limits

The `resources` block bounds each task container: `cpus`, `memory`, `pids`,
`network` (`none` by default), and `agent_timeout_s`. `disk_quota` (for example
`"5g"`) is enforced when the host's storage driver supports it (overlay2 on xfs
with pquota, or btrfs); on drivers that don't, reforge logs a warning and runs
without the quota rather than failing.

For tasks that need real credentials, list the host env var names under
`environment.allowed_env` (values never go in task.yaml). They reach the container
only when the run also passes `--env-passthrough KEY`. See
[SECURITY.md](../SECURITY.md).

For tasks that need the network but only for a few hosts, set a network and list the
allowed domains under `environment.allowed_hosts`:

```yaml
environment:
  allowed_hosts: [pypi.org, files.pythonhosted.org]
resources:
  network: bridge
```

reforge routes the task through a filtering proxy that permits those hosts (and their
subdomains) and refuses everything else. With `network: none` the allowlist has
nothing to act on, so `reforge validate` flags that combination.

## Validate before you run

```bash
reforge validate my-task     # schema + files exist + scoring inputs present
reforge verify-gold my-task  # the gold solution actually resolves it
```

If a task's tests touch anything non-deterministic (time, network, ordering), run the
gold solution a few times to catch it before it skews a leaderboard:

```bash
reforge verify-gold my-task --repeats 5  # fails if resolution/score/tests vary
```
