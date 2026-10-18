#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[1/6] Vagrant machine state"
vagrant status

echo "[2/6] V1 load distribution across four application servers"
python3 scripts/ops.py v1

echo "[3/6] R5 PostgreSQL streaming replication"
python3 scripts/ops.py replication

echo "[4/6] V3 four-server benchmark with Redis disabled"
python3 scripts/ops.py cache-off
python3 scripts/ops.py benchmark --label V3-N4

echo "[5/6] E3 warm Redis cache benchmark"
python3 scripts/ops.py cache-on
python3 scripts/ops.py cache-purge
python3 - <<'PY'
import json
import urllib.request

url = 'http://127.0.0.1:8080/resultat?matricule=000001'
with urllib.request.urlopen(url, timeout=10) as response:
    if response.status != 200:
        raise SystemExit(f'Cache warm-up returned HTTP {response.status}')
    json.loads(response.read())
PY
python3 scripts/ops.py benchmark --label E3-warm-cache

echo "[6/6] R2 idempotent provisioning"
python3 scripts/ops.py idempotence

echo "Core validation completed. Evidence is in results/."
