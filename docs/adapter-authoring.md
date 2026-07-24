# Writing an adapter

An adapter drives one agent inside a task container. It's the only place that knows
how a particular agent is invoked, so supporting a new tool or model means writing
a small class rather than touching the harness.

## The contract

Implement `AgentAdapter` from `reforge.adapters.base`:

```python
from reforge.adapters.base import AdapterInput, AdapterResult, AgentAdapter


class MyAdapter(AgentAdapter):
    name = "my-agent"
    version = "1.0.0"

    def validate(self, input: AdapterInput) -> None:
        # Fail fast: check API keys, the model is supported, the CLI is installed.
        ...

    def run(self, input: AdapterInput) -> AdapterResult:
        # Drive the agent to edit files under input.workspace_path in the container.
        result = input.container.exec(
            ["my-agent", "--prompt", input.instruction],
            workdir=input.workspace_path,
            env=input.env,
            timeout_s=input.timeout_s,
            stream_to=input.trace_path,
        )
        return AdapterResult(
            success=result.ok,
            trace_path=input.trace_path,
            exit_code=result.exit_code,
        )
```

## What an adapter does and doesn't do

- It **does** change files in the workspace and write a trace of what the agent did.
- It **doesn't** compute scores, and it **doesn't** report the diff. The harness
  captures the diff with git after `run` returns, the same way for every adapter.
  This keeps a one-line CLI wrapper and a full agent on equal footing.

`success` means the agent *ran to completion*, not that it *solved the task*. Whether
it solved anything is decided later by the scorers.

## What you get in `AdapterInput`

- `instruction`: the task prompt.
- `workspace_path`: where the code lives in the container (usually `/workspace`).
- `container`: an exec/copy handle into the running container.
- `trace_path`: a host file to stream the agent's output to.
- `model`, `config`, `env`, `timeout_s`: model id, adapter-specific options,
  environment (API keys), and the agent time budget.

## Registering it

Adapters are discovered through the `reforge.adapters` entry-point group. In your
`pyproject.toml`:

```toml
[project.entry-points."reforge.adapters"]
my-agent = "my_package.adapter:MyAdapter"
```

Once installed, it appears in `reforge list adapters` and can be used with
`reforge run --adapter my-agent`. A third-party adapter is just a package someone
installs; you never need to fork reforge to add one.

## Testing your adapter

The `noop` and `gold` adapters in `reforge.adapters` are the simplest working
examples. To sanity-check yours end to end, point it at the tiny task:

```bash
reforge run --task tests/fixtures/tiny-task --adapter my-agent --model <model>
```
