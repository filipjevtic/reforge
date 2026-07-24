#!/bin/sh
# Run the held-out analytics tests against the agent's workspace.
set -e
cd /verifier/tests
PYTHONPATH=/workspace pytest test_analytics.py \
  --junitxml="${REFORGE_REPORT:-/tmp/reforge_report}" -o junit_family=xunit2
