#!/usr/bin/env bash
#
# Cloud Agent install script for the Dream Analysis Bot.
# Idempotent: prepares system packages, a local PostgreSQL role/database
# (peer auth, no secrets needed), and the Python virtualenv with dependencies.
set -euo pipefail

# Resolve the repository root regardless of where the script is invoked from.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Installing system packages (PostgreSQL + Python venv toolchain)"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq
sudo apt-get install -y -qq postgresql postgresql-contrib python3-venv python3-dev

# Detect the installed PostgreSQL major version (defaults to 16).
PG_VER="$(pg_lsclusters -h 2>/dev/null | awk 'NR==1{print $1}')"
: "${PG_VER:=16}"

echo "==> Ensuring PostgreSQL cluster ${PG_VER}/main is running"
sudo pg_ctlcluster "$PG_VER" main start 2>/dev/null || true
for _ in $(seq 1 30); do
  pg_isready -q && break
  sleep 1
done
pg_isready

# Provision a role + database that match the current OS user so the app can
# connect over the local unix socket using peer auth. The app reads PG* from the
# environment; when unset, libpq/psycopg2 fall back to these local defaults.
DB_USER="$(id -un)"
echo "==> Ensuring PostgreSQL role and database '${DB_USER}' exist"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 \
  || sudo -u postgres createuser --superuser "${DB_USER}"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_USER}'" | grep -q 1 \
  || sudo -u postgres createdb -O "${DB_USER}" "${DB_USER}"

echo "==> Creating Python virtualenv and installing dependencies"
if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "==> install.sh complete"
