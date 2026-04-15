#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HERMES_DIR=${HOME}/.hermes/hermes-agent
CONFIG_PATH=${HOME}/.hermes/config.yaml

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hermes-dir)
      HERMES_DIR="$2"
      shift 2
      ;;
    --config)
      CONFIG_PATH="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

python3 - "$ROOT_DIR" "$CONFIG_PATH" <<'PY'
import sys
from pathlib import Path
import yaml

repo_root = Path(sys.argv[1]).expanduser().resolve()
config_path = Path(sys.argv[2]).expanduser()
config_path.parent.mkdir(parents=True, exist_ok=True)
if config_path.exists():
    data = yaml.safe_load(config_path.read_text(encoding='utf-8')) or {}
else:
    data = {}
skills = data.setdefault('skills', {})
external_dirs = skills.setdefault('external_dirs', [])
repo_str = str(repo_root)
if repo_str not in external_dirs:
    external_dirs.append(repo_str)
config_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding='utf-8')
print(f'Updated {config_path} with skills.external_dirs += {repo_str}')
PY

"${ROOT_DIR}/scripts/apply-hermes-patch.sh" --hermes-dir "$HERMES_DIR"

echo "styled-voice install complete"
