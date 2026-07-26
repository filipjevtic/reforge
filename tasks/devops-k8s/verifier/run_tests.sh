#!/bin/sh
set -e
cd /verifier/tests
pytest test_service.py --junitxml="${REFORGE_REPORT:-/tmp/reforge_report}" -o junit_family=xunit2
