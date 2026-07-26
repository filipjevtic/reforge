#!/bin/sh
set -e
cd /verifier/tests
pytest test_slugify.py --junitxml="${REFORGE_REPORT:-/tmp/reforge_report}" -o junit_family=xunit2
