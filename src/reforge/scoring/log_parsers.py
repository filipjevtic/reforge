"""Parse machine-readable test output into per-test pass/fail status.

We never scrape human-readable console output. Frameworks are asked to emit a
structured report (JUnit XML for pytest/jest, ``go test -json`` later) and we map
it back to the node ids the task author listed in ``fail_to_pass`` /
``pass_to_pass``.
"""

from __future__ import annotations

from enum import StrEnum
from xml.etree import ElementTree

from reforge.utils.errors import ScoringError


class TestStatus(StrEnum):
    passed = "PASS"
    failed = "FAIL"
    error = "ERROR"
    skipped = "SKIP"


class TestCaseResult:
    __slots__ = ("nodeid", "status")

    def __init__(self, nodeid: str, status: TestStatus) -> None:
        self.nodeid = nodeid
        self.status = status

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"TestCaseResult({self.nodeid!r}, {self.status.value})"


def parse_junit_xml(xml_text: str) -> list[TestCaseResult]:
    """Parse a JUnit/xUnit2 XML document (pytest ``--junitxml``, jest junit)."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise ScoringError(f"could not parse JUnit XML: {exc}") from exc

    results: list[TestCaseResult] = []
    for case in root.iter("testcase"):
        nodeid = _nodeid_for(case)
        results.append(TestCaseResult(nodeid, _status_for(case)))
    return results


def _status_for(case: ElementTree.Element) -> TestStatus:
    if case.find("error") is not None:
        return TestStatus.error
    if case.find("failure") is not None:
        return TestStatus.failed
    if case.find("skipped") is not None:
        return TestStatus.skipped
    return TestStatus.passed


def _nodeid_for(case: ElementTree.Element) -> str:
    """Reconstruct a pytest-style node id from a testcase element."""
    name = case.get("name", "")
    classname = case.get("classname", "")
    file_attr = case.get("file")

    if file_attr and file_attr.endswith(".py"):
        module = file_attr[:-3].replace("/", ".")
        if classname == module:
            return f"{file_attr}::{name}"
        if classname.startswith(module + "."):
            cls = classname[len(module) + 1 :].replace(".", "::")
            return f"{file_attr}::{cls}::{name}"
        return f"{file_attr}::{name}"

    if classname:
        return f"{classname}::{name}"
    return name


def match_status(expected_id: str, results: list[TestCaseResult]) -> TestStatus | None:
    """Find the status for a task-declared test id, tolerating id-format drift.

    Frameworks report node ids inconsistently: pytest's JUnit output uses a
    dotted module classname with no ``.py`` (``test_calc::test_add``), while task
    authors naturally write path-style ids (``test_calc.py::test_add``). We
    normalize both to a dotted, extension-free form and compare exactly, then by
    suffix (so a rootdir prefix on either side still matches).
    """
    by_id = {r.nodeid: r.status for r in results}
    if expected_id in by_id:
        return by_id[expected_id]

    want = _normalize_id(expected_id)
    for r in results:
        have = _normalize_id(r.nodeid)
        if want == have or have.endswith("." + want) or want.endswith("." + have):
            return r.status
    return None


def _normalize_id(node_id: str) -> str:
    """Collapse ``path/mod.py::Class::test`` and ``mod.Class.test`` to one form."""
    return node_id.replace(".py", "").replace("::", ".").replace("/", ".").strip(".")
