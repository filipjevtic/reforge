# Tasks

This directory holds shipped benchmark tasks. Point `reforge run --dataset ./tasks`
at it to run the whole set.

Each task is its own directory with a `task.yaml`, a `Dockerfile`, a `verifier/`,
and a `gold/` solution. For a complete minimal example, see
[`tests/fixtures/tiny-task`](../tests/fixtures/tiny-task). To write your own, read
[docs/task-authoring.md](../docs/task-authoring.md).

Shipped tasks:

- `newfeature-analytics`: build a net-new analytics module over an internal events
  dataset (a new-feature task; scored on tests, the `app.events` import it must
  wire up, and a rubric).
- `replication-staging-env`: create a staging environment that mirrors prod (a
  replication task; the dependency-coverage scorer reports any service or config
  key the agent forgets).

Every task here is checked in CI: its gold solution must resolve it
(`reforge verify-gold <task>`).
