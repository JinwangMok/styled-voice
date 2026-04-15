#!/usr/bin/env bash
set -euo pipefail

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

cd "$HERMES_DIR"
source venv/bin/activate
python -m pytest tests/gateway/test_styled_voice_audio_paths.py -q
