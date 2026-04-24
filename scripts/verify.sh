#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HERMES_DIR=${HOME}/.hermes/hermes-agent
PYTHON_BIN=${HERMES_PYTHON_BIN:-}
PYTEST_PYTHON=${HERMES_VERIFY_PYTHON:-}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hermes-dir)
      HERMES_DIR="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$PYTEST_PYTHON" ]]; then
  if python3 -c 'import pytest' >/dev/null 2>&1; then
    PYTEST_PYTHON="python3"
  elif [[ -x "$HOME/.hermes/hermes-agent/venv/bin/python" ]]; then
    PYTEST_PYTHON="$HOME/.hermes/hermes-agent/venv/bin/python"
  else
    echo "Could not find a Python interpreter with pytest installed" >&2
    exit 1
  fi
fi

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$HERMES_DIR/venv/bin/python" ]]; then
    PYTHON_BIN="$HERMES_DIR/venv/bin/python"
  elif [[ -x "$HOME/.hermes/hermes-agent/venv/bin/python" ]]; then
    PYTHON_BIN="$HOME/.hermes/hermes-agent/venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

echo "==> Running styled-voice repo tests"
cd "$ROOT_DIR"
"$PYTEST_PYTHON" -m pytest tests/test_styled_voice_request.py -q
python3 scripts/styled_voice_request.py --help >/dev/null

echo "==> Verifying /styled-voice skill discovery"
cd "$HERMES_DIR"
"$PYTHON_BIN" - <<'PY'
from agent.skill_commands import scan_skill_commands
entry = scan_skill_commands().get('/styled-voice')
if not entry:
    raise SystemExit('/styled-voice not discovered')
print(entry)
PY
