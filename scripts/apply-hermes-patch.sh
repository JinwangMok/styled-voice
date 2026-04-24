#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PATCH_PATH="${ROOT_DIR}/patches/hermes-gateway-styled-voice.patch"
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

if [[ ! -d "$HERMES_DIR/.git" ]]; then
  echo "Hermes git repo not found at: $HERMES_DIR" >&2
  exit 1
fi

if git -C "$HERMES_DIR" apply --reverse --check "$PATCH_PATH" >/dev/null 2>&1; then
  echo "Patch already applied in $HERMES_DIR"
  exit 0
fi

if git -C "$HERMES_DIR" apply --3way --check "$PATCH_PATH" >/dev/null 2>&1; then
  git -C "$HERMES_DIR" apply --3way "$PATCH_PATH"
  echo "Applied styled-voice Hermes patch to $HERMES_DIR"
  exit 0
fi

echo "Patch no longer applies cleanly. Refresh the styled-voice bundle instead of editing Hermes directly." >&2
exit 1
