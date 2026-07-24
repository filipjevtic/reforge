#!/bin/sh
# Run the held-out tests and write a JUnit report to $REFORGE_REPORT.
# The workspace (with the agent's changes) is on PYTHONPATH so tests can import it.
set -e
cd /verifier/tests
PYTHONPATH=/workspace pytest test_calc.py --junitxml="${REFORGE_REPORT:-/tmp/reforge_report.xml}" -o junit_family=xunit2
