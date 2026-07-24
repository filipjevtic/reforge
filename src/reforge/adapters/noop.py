"""The no-op adapter: changes nothing.

Used to prove the harness is not a false-positive machine. A run with ``noop``
must come back unresolved with zero FAIL_TO_PASS tests passing.
"""

from __future__ import annotations

from reforge.adapters.base import AdapterInput, AdapterResult, AgentAdapter


class NoopAdapter(AgentAdapter):
    name = "noop"
    version = "1.0.0"

    def run(self, input: AdapterInput) -> AdapterResult:
        input.trace_path.write_text("noop adapter made no changes\n", encoding="utf-8")
        return AdapterResult(success=True, trace_path=input.trace_path, exit_code=0)
