#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HERMES_DIR=${HOME}/.hermes/hermes-agent

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

echo "==> Running styled-voice repo tests"
cd "$ROOT_DIR"
python3 -m pytest tests/test_styled_voice_request.py -q

echo "==> Running Hermes gateway patch verification"
cd "$HERMES_DIR"
source venv/bin/activate
python -m pytest tests/gateway/test_styled_voice_audio_paths.py -q

echo "==> Verifying /styled-voice skill discovery"
python - <<'PY'
from agent.skill_commands import scan_skill_commands
entry = scan_skill_commands().get('/styled-voice')
if not entry:
    raise SystemExit('/styled-voice not discovered')
print(entry)
PY
