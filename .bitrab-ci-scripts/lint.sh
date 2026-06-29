#!/usr/bin/env bash
set -euo pipefail
source ./.bitrab-ci-scripts/setup.sh
uv run isort --check-only keynest tests
uv run black --check keynest tests
uv run ruff check --quiet keynest tests
uv run pylint --score=n --reports=n --rcfile=.pylintrc keynest
uv run pylint --score=n --reports=n --rcfile=.pylintrc_tests tests
