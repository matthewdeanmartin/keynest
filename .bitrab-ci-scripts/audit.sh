#!/usr/bin/env bash
set -euo pipefail
source ./.bitrab-ci-scripts/setup.sh
# Advisories accepted with no available fix (kept in sync with the Makefile
# AUDIT_IGNORE list):
#   GHSA-p4gq-832x-fm9v: nltk path traversal, transitive dev-only dep via
#     pydoclint->textstat. No fixed release.
AUDIT_IGNORE="GHSA-p4gq-832x-fm9v"
echo "=== uv audit ==="
uv audit --ignore-until-fixed "${AUDIT_IGNORE}"
echo "=== pip-audit ==="
uv run pip-audit --ignore-vuln "${AUDIT_IGNORE}"
