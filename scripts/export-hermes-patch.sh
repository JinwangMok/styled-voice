#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HERMES_DIR=${HOME}/.hermes/hermes-agent
SOURCE_REF='stash@{0}'
STYLE_COMMIT='41231226'
OUTPUT_PATH="$ROOT_DIR/patches/hermes-gateway-styled-voice.patch"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hermes-dir)
      HERMES_DIR="$2"
      shift 2
      ;;
    --source-ref)
      SOURCE_REF="$2"
      shift 2
      ;;
    --style-commit)
      STYLE_COMMIT="$2"
      shift 2
      ;;
    --output)
      OUTPUT_PATH="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT
mkdir -p "$(dirname "$OUTPUT_PATH")"

HELPER_PATCH="$TMPDIR/helper-styled.patch"
git -C "$ROOT_DIR" show HEAD:patches/hermes-gateway-styled-voice.patch > "$HELPER_PATCH"

git clone --quiet "$HERMES_DIR" "$TMPDIR/repo"
git -C "$TMPDIR/repo" checkout --quiet origin/main
git -C "$TMPDIR/repo" apply --3way "$HELPER_PATCH"

for rel in tools/tts_tool.py tests/tools/test_managed_media_gateways.py; do
  mkdir -p "$TMPDIR/repo/$(dirname "$rel")"
  git -C "$HERMES_DIR" show "$SOURCE_REF:$rel" > "$TMPDIR/repo/$rel"
done

git -C "$TMPDIR/repo" diff --binary origin/main -- \
  gateway/run.py \
  tests/gateway/test_styled_voice_audio_paths.py \
  tools/tts_tool.py \
  tests/tools/test_managed_media_gateways.py > "$OUTPUT_PATH"

echo "Wrote: $OUTPUT_PATH"
