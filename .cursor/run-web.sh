#!/usr/bin/env bash
#
# Runs the FastAPI webhook server for the Dream Analysis Bot.
# The bot needs TELEGRAM_TOKEN and OPENAI_API_KEY (add them as Secrets). When
# they are absent the server is not started, so this terminal does not crash-loop.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ -n "${TELEGRAM_TOKEN:-}" ] && [ -n "${OPENAI_API_KEY:-}" ]; then
  echo "==> Starting Dream Analysis Bot on port ${PORT:-8000}"
  exec .venv/bin/uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"
else
  echo "TELEGRAM_TOKEN and/or OPENAI_API_KEY are not set."
  echo "Add them as Secrets to run the live bot; PostgreSQL and dependencies are ready."
  echo "This terminal is idle. Re-run '.cursor/run-web.sh' after adding the secrets."
  tail -f /dev/null
fi
