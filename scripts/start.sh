#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/setup.py
python3 scripts/ops.py preflight
vagrant validate
vagrant up --provider=virtualbox
python3 scripts/ops.py v1
