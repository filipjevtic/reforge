"""Deterministic test scorer (SWE-bench FAIL_TO_PASS / PASS_TO_PASS).

The verifier entrypoint is expected to run the test framework and write a JUnit
XML report to the path in ``$REFORGE_REPORT``. We then map the report back to the
test ids the task declared:

* ``F2P`` = fraction of ``fail_to_pass`` tests that now pass.
* ``P2P`` = whether every ``pass_to_pass`` test still passes.

A task counts as *resolved* when F2P == 1.0 and P2P holds, the same bar
SWE-bench uses.
"""

from __future__ import annotations

from reforge.scoring.base import Scorer, ScorerResult, TaskScoringContext
from reforge.scoring.log_parsers import TestStatus, match_status, parse_junit_xml
from reforge.utils.errors import ScoringError
from reforge.utils.logging import get_logger

VERIFIER_DIR_IN_CONTAINER = "/verifier"
REPORT_PATH = "/tmp/reforge_report.xml"

log = get_logger("scoring.tests")


class TestScorer(Scorer):
    key = "tests"

    def score(self, ctx: TaskScoringContext) -> ScorerResult:
        spec = ctx.spec
        entrypoint = _in_container_entrypoint(spec.verification.entrypoint)

        exec_result = ctx.container.exec(
            ["sh", entrypoint],
            workdir=ctx.workspace_path,
            env={"REFORGE_REPORT": REPORT_PATH},
            timeout_s=spec.verification.timeout_s,
        )

        try:
            report_xml = ctx.container.read_file(REPORT_PATH).decode("utf-8", errors="replace")
        except Exception as exc:
            raise ScoringError(
                f"verifier did not produce a report at {REPORT_PATH}: {exc}. "
                f"Entrypoint exited {exec_result.exit_code}. "
                "The verifier script must write JUnit XML to $REFORGE_REPORT."
            ) from exc

        results = parse_junit_xml(report_xml)

        f2p_detail: dict[str, str] = {}
        f2p_passed = 0
        for test_id in spec.verification.fail_to_pass:
            status = match_status(test_id, results)
            f2p_detail[test_id] = status.value if status else "MISSING"
            if status is TestStatus.passed:
                f2p_passed += 1

        p2p_detail: dict[str, str] = {}
        p2p_ok = True
        for test_id in spec.verification.pass_to_pass:
            status = match_status(test_id, results)
            p2p_detail[test_id] = status.value if status else "MISSING"
            if status is not TestStatus.passed:
                p2p_ok = False

        total_f2p = len(spec.verification.fail_to_pass)
        f2p_ratio = (f2p_passed / total_f2p) if total_f2p else 1.0
        resolved = f2p_ratio == 1.0 and p2p_ok

        return ScorerResult(
            key=self.key,
            score=f2p_ratio,
            passed=resolved,
            detail={
                "fail_to_pass": f2p_detail,
                "pass_to_pass": p2p_detail,
                "pass_to_pass_ok": p2p_ok,
                "f2p_passed": f2p_passed,
                "f2p_total": total_f2p,
                "verifier_exit_code": exec_result.exit_code,
                "verifier_timed_out": exec_result.timed_out,
            },
        )


def _in_container_entrypoint(entrypoint: str) -> str:
    """Map a task-dir-relative verifier entrypoint to its in-container path."""
    prefix = "verifier/"
    rel = entrypoint[len(prefix) :] if entrypoint.startswith(prefix) else entrypoint
    return f"{VERIFIER_DIR_IN_CONTAINER}/{rel}"
