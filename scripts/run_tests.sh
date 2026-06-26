#!/usr/bin/env bash
# Test runner with colon-separated arg translation. Called from `make test`.
#
#   make test                                → all tests (full suite)
#   make test <app>                          → all tests in apps/<app>/tests/
#   make test <app>:<file>                   → all tests in apps/<app>/tests/<file>.py
#   make test <app>:<file>:<test_name>       → single test (pytest -k <test_name>)
#
# The test_name is matched via pytest's -k (keyword expression) so callers
# don't need to remember the test's class. Bare method-name matches work.

set -euo pipefail

PYTEST=(".venv/bin/python" "-m" "pytest")

if [ $# -eq 0 ]; then
    exec "${PYTEST[@]}"
fi

arg="$1"
IFS=':' read -r app file test_name <<< "$arg"

if [ -z "${app:-}" ]; then
    echo "Error: missing app name. Usage: make test <app>[:<file>[:<test_name>]]" >&2
    exit 2
fi

path="apps/$app/tests/"
if [ ! -d "$path" ]; then
    echo "Error: $path does not exist" >&2
    exit 2
fi

if [ -n "${file:-}" ]; then
    path="${path}${file}.py"
    if [ ! -f "$path" ]; then
        echo "Error: $path does not exist" >&2
        exit 2
    fi
fi

if [ -n "${test_name:-}" ]; then
    exec "${PYTEST[@]}" "$path" -k "$test_name"
else
    exec "${PYTEST[@]}" "$path"
fi
