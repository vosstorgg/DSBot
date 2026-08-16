#!/usr/bin/env bash
#
# Cloud Agent start script for the Dream Analysis Bot.
# Runs on every boot: brings the local PostgreSQL cluster online (idempotent)
# and waits until it is accepting connections.
set -euo pipefail

PG_VER="$(pg_lsclusters -h 2>/dev/null | awk 'NR==1{print $1}')"
: "${PG_VER:=16}"

if ! pg_isready -q; then
  echo "==> Starting PostgreSQL cluster ${PG_VER}/main"
  sudo pg_ctlcluster "$PG_VER" main start || true
fi

for _ in $(seq 1 30); do
  pg_isready -q && break
  sleep 1
done

pg_isready
echo "==> start.sh complete: PostgreSQL is ready"
