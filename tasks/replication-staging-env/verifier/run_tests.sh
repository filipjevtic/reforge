#!/bin/sh
# Verify the staging environment mirrors prod, and prod is untouched.
set -e
cd /verifier/tests
pytest test_staging.py test_prod.py \
  --junitxml="${REFORGE_REPORT:-/tmp/reforge_report}" -o junit_family=xunit2
