"""Parse machine-readable test output into per-test pass/fail status.

We never scrape human-readable console output. Frameworks are asked to emit a
structured report (JUnit XML for pytest/jest, ``go test -json`` later) and we map
it back to the node ids the task author listed in ``fail_to_pass`` /
``pass_to_pass``.
"""

from __future__ import annotations

import re
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


def parse_go_json(text: str) -> list[TestCaseResult]:
    """Parse ``go test -json`` output (one JSON object per line)."""
    import json

    status_map = {"pass": TestStatus.passed, "fail": TestStatus.failed, "skip": TestStatus.skipped}
    latest: dict[str, TestStatus] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        test = event.get("Test")
        action = event.get("Action")
        if not test or action not in status_map:
            continue
        pkg = event.get("Package", "")
        nodeid = f"{pkg}::{test}" if pkg else test
        latest[nodeid] = status_map[action]
    return [TestCaseResult(nodeid, status) for nodeid, status in latest.items()]


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
    authors naturally write path-style ids (``test_calc.py::test_add``). We split
    both into segments and match when one is a trailing slice of the other, which
    absorbs a rootdir/directory prefix drift on either side.

    To avoid collisions we require at least two shared trailing segments (module +
    test), so a bare ``test_add`` reported from an unrelated module can never be
    credited to a more-qualified ``pkg.mod::test_add``.
    """
    by_id = {r.nodeid: r.status for r in results}
    if expected_id in by_id:
        return by_id[expected_id]

    want = _segments(expected_id)
    parsed = [(_segments(r.nodeid), r.status) for r in results]

    # 1) exact segment match, and 2) qualified suffix match (both sides carry the
    # module, sharing >= 2 trailing segments) absorb rootdir/dir prefix drift.
    for have, status in parsed:
        if have == want:
            return status
    for have, status in parsed:
        n = min(len(want), len(have))
        if n >= 2 and want[-n:] == have[-n:]:
            return status

    # 3) a deliberately-bare declared id (e.g. a go ``TestAdd``) matches on the
    # function name, but only when exactly one test carries it, so it never
    # silently credits the wrong module. A qualified id gets no such fallback.
    if len(want) == 1:
        tail = want[0]
        hits = [status for have, status in parsed if have and have[-1] == tail]
        if len(hits) == 1:
            return hits[0]
    return None


_PY_EXT = re.compile(r"\.py(?=$|[:./])")


def _segments(node_id: str) -> list[str]:
    """Split ``path/mod.py::Class::test`` or ``mod.Class.test`` into segments.

    The ``.py`` extension is stripped only where it is an extension (end of a path
    segment), never mid-identifier, so a module like ``test_python`` is preserved.
    """
    stripped = _PY_EXT.sub("", node_id)
    flat = stripped.replace("::", ".").replace("/", ".")
    return [p for p in flat.split(".") if p]
