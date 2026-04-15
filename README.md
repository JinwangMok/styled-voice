# styled-voice

External Hermes skill for Discord voice cloning with VoxCPM, packaged **outside** the Hermes core repo.

This repository is intentionally split into two layers:

1. **External skill** — the repo root is a Hermes skill (`SKILL.md`).
2. **Runtime patch bundle** — a tiny patch against Hermes runtime that exposes cached local audio attachment paths **only for `/styled-voice` requests**.

That means you can keep using the upstream Hermes codebase as-is, and apply a local patch from this repo instead of maintaining a long-lived fork.

## What it does

- uses direct VoxCPM endpoint: `http://10.40.40.40:9100/v1/audio/speech`
- accepts Discord audio attachments as reference clips
- handles ugly real-world Discord cache artifacts by normalizing audio with `ffmpeg` when needed
- returns Discord-playable OGG/Opus output
- keeps the feature packaged outside the Hermes upstream repository

## Repository layout

```text
styled-voice/
├── SKILL.md                                   # external Hermes skill (repo root)
├── README.md
├── patches/
│   └── hermes-gateway-styled-voice.patch      # tiny runtime patch for Hermes
├── references/
│   └── architecture.md                        # design notes and rationale
└── scripts/
    ├── apply-hermes-patch.sh                  # idempotent patch apply helper
    ├── install.sh                             # config + patch setup helper
    └── verify.sh                              # run focused verification in Hermes
```

## Install

### 1. Clone this repo

```bash
git clone https://github.com/JinwangMok/styled-voice.git ~/workspace/styled-voice
```

### 2. Register it as an external Hermes skill and apply the runtime patch

```bash
cd ~/workspace/styled-voice
./scripts/install.sh --hermes-dir ~/.hermes/hermes-agent --config ~/.hermes/config.yaml
```

What `install.sh` does:

- adds this repo root to `skills.external_dirs` in your Hermes config
- applies `patches/hermes-gateway-styled-voice.patch` to your local Hermes checkout
- leaves upstream git remotes untouched

### 3. Verify

```bash
./scripts/verify.sh --hermes-dir ~/.hermes/hermes-agent
```

## Runtime patch scope

The patch is deliberately tiny.

It adds:

- `_is_styled_voice_request()`
- `_build_audio_attachment_path_note()`
- a conditional branch in `GatewayRunner._prepare_inbound_message_text(...)`
- focused tests in `tests/gateway/test_styled_voice_audio_paths.py`

It does **not** add a hardcoded feature-specific slash command or bake VoxCPM logic into Hermes core. Hermes just exposes cached audio file paths when `/styled-voice` is invoked; the external skill handles the rest.

## Usage

In Discord, attach 1-3 voice samples and invoke:

```text
/styled-voice 유빈아, 안녕? 나는 진왕이형 목소리를 따라하고 있는 보라매 봇이야.
```

The skill will:

1. read injected cached attachment paths
2. normalize weird Discord audio if needed
3. call direct VoxCPM
4. convert result to OGG/Opus
5. return the generated voice clip

## Notes

- direct backend is used on purpose; nginx `/tts/...` was unhealthy during validation
- this repo is both a git repo and a Hermes external skill root
- if upstream Hermes changes around `gateway/run.py`, re-generate or refresh the patch in `patches/`
