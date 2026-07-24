# Tasks

This directory holds shipped benchmark tasks. Point `reforge run --dataset ./tasks`
at it to run the whole set.

Each task is its own directory with a `task.yaml`, a `Dockerfile`, a `verifier/`,
and a `gold/` solution. For a complete minimal example, see
[`tests/fixtures/tiny-task`](../tests/fixtures/tiny-task). To write your own, read
[docs/task-authoring.md](../docs/task-authoring.md).

Sample replication and new-feature tasks land here as those milestones complete.
Every task in this directory is checked in CI: its gold solution must resolve it
(`reforge verify-gold <task>`).
