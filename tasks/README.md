# Tasks

This directory holds shipped benchmark tasks. Point `reforge run --dataset ./tasks`
at it to run the whole set.

Each task is its own directory with a `task.yaml`, a `Dockerfile`, a `verifier/`,
and a `gold/` solution. For a complete minimal example, see
[`tests/fixtures/tiny-task`](../tests/fixtures/tiny-task). To write your own, read
[docs/task-authoring.md](../docs/task-authoring.md).

Shipped tasks (a starter cookbook across domains):

- `newfeature-analytics`: build a net-new analytics module over an internal events
  dataset (new-feature; scored on tests, the `app.events` import, and a rubric).
- `replication-staging-env`: create a staging environment that mirrors prod
  (replication/devops; dependency-coverage reports any service or config key missed).
- `cloud-infra-terraform`: add an S3 bucket resource to a Terraform config
  (cloud-infra; uses the `terraform_refs` detector).
- `devops-k8s`: add a Kubernetes Service for a Deployment (devops; uses the
  `k8s_refs` detector).
- `newfeature-js-slug`: add a slugify module that reuses lodash (app-feature; uses the
  `js_imports` detector).
- `newfeature-go-uuid`: add a UUID id generator that reuses google/uuid (app-feature;
  uses the `go_imports` detector).

Start your own with `reforge init <id> --category <domain>`.

Every task here is checked in CI: its gold solution must resolve it
(`reforge verify-gold <task>`).
