"""Unit test for the verify-gold flakiness detector."""

from __future__ import annotations

from reforge.cli import _flaky_tests
from reforge.report.models import SubScore, TaskResult


def _result(add_status: str) -> TaskResult:
    return TaskResult(
        task_id="t",
        category="c",
        adapter="gold",
        resolved=add_status == "PASS",
        scores={
            "tests": SubScore(
                score=1.0,
                passed=add_status == "PASS",
                detail={
                    "fail_to_pass": {"m.py::test_add": add_status},
                    "pass_to_pass": {"m.py::test_keep": "PASS"},
                },
            )
        },
    )


def test_flaky_detects_status_variation() -> None:
    # test_add flips between runs -> flaky; test_keep is stable -> not flagged.
    results = [_result("PASS"), _result("FAIL"), _result("PASS")]
    assert _flaky_tests(results) == ["m.py::test_add"]


def test_no_flakiness_when_stable() -> None:
    results = [_result("PASS"), _result("PASS")]
    assert _flaky_tests(results) == []
