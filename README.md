# styled-voice

External Hermes skill for Discord voice cloning with VoxCPM, packaged **outside** the Hermes core repo.

This repository is intentionally external-only:

1. **External skill** — the repo root is a Hermes skill (`SKILL.md`).
2. **Helper/runtime tooling** — helper scripts live here, but the install flow no longer patches Hermes runtime.

That means you can keep using the upstream Hermes codebase as-is without maintaining a long-lived fork or local runtime patch.

## What it does

- uses direct VoxCPM endpoint: `http://10.40.40.40:9100/v1/audio/speech`
- accepts Discord audio attachments as reference clips
- handles ugly real-world Discord cache artifacts by normalizing audio with `ffmpeg` when needed
- retries automatically with normalized WAV inputs if direct upload fails or looks suspicious
- surfaces backend errors more clearly when the response is non-audio or upstream fails
- returns Discord-playable OGG/Opus output
- keeps the feature packaged outside the Hermes upstream repository

## Repository layout

```text
styled-voice/
├── SKILL.md                                   # external Hermes skill (repo root)
├── README.md
├── patches/
│   └── hermes-gateway-styled-voice.patch      # archived historical patch snapshot (not applied by current install)
├── references/
│   ├── architecture.md                        # design notes and rationale
│   ├── operations.md                          # operational playbook / known issues
│   └── v1.1-handoff.md                        # current handoff / follow-up context
├── scripts/
│   ├── apply-hermes-patch.sh                  # archived helper from the old patch-based flow
│   ├── install.sh                             # config + patch setup helper
│   ├── styled_voice_request.py                # direct→normalize-retry helper
│   └── verify.sh                              # repo + skill-discovery verification helper
└── tests/
    └── test_styled_voice_request.py           # helper-script regression tests
```

## Install

### 1. Clone this repo

```bash
git clone https://github.com/JinwangMok/styled-voice.git ~/workspace/styled-voice
```

### 2. Register it as an external Hermes skill

```bash
cd ~/workspace/styled-voice
./scripts/install.sh --hermes-dir ~/.hermes/hermes-agent --config ~/.hermes/config.yaml
```

What `install.sh` does:

- adds this repo root to `skills.external_dirs` in your Hermes config
- leaves the Hermes checkout untouched

### 3. Verify

```bash
./scripts/verify.sh --hermes-dir ~/.hermes/hermes-agent
```

## External-only contract

The current install flow does **not** patch Hermes runtime.

That means `/styled-voice` may only use audio file paths or URLs that Hermes already exposes in message context, or paths explicitly supplied by an operator. It must **not** rely on hidden local cache-path injection from patched gateway code.

## Discord-first usage

### Fast user-facing form

Attach **1-3 short voice samples** and write:

```text
/styled-voice 생성할 문장
```

Example:

```text
/styled-voice 유빈아, 안녕? 나는 진왕이형 목소리를 따라하고 있는 보라매 봇이야.
```

### What the skill assumes by default

- every attached audio clip is treated as `reference_audio`
- the text after `/styled-voice` is the sentence to synthesize
- if you include a style phrase, it is passed as `style_prompt`
- the backend is called directly, not through nginx `/tts/...`
- final output is always converted to OGG/Opus for Discord playback

### Recommended sample quality

- 3-15 seconds per clip is usually enough
- avoid loud music / overlapping speakers
- cleaner speech beats longer speech
- 1 good clip > 3 noisy clips

## Discord style cheat sheet

Users do not need special syntax, but these phrasing patterns work well as style hints.

### Softer / gentler

- `부드럽고 조심스럽게`
- `soft, warm, gentle`
- `차분하고 다정하게`

### More hesitation / thinking pauses

- `살짝 망설이듯`
- `조금 생각하면서 천천히`
- `with small pauses, slightly hesitant`

### Slower pacing

- `조금 느리게`
- `또박또박, 급하지 않게`
- `slow, measured, unhurried`

### Whisperier / breathier

- `작게 속삭이듯`
- `숨결이 조금 섞인 느낌으로`
- `soft whispery tone`

### Brighter / smiling

- `살짝 웃는 느낌으로`
- `밝고 편안하게`
- `slightly smiling, conversational`

### Combined examples

- `차분하고 부드럽게, 살짝 웃는 느낌으로`
- `조금 느리게, 망설이듯, 조심스럽게`
- `soft, careful, slightly whispery, with small pauses`

## Automatic retry / normalize flow

The robust path for real Discord uploads is now explicit:

1. inspect extracted audio paths with `ffprobe`
2. classify whether direct upload looks safe
3. try direct upload when the files look normal
4. if upload fails, response is non-audio, or the cache looks suspicious, normalize inputs to mono WAV with `ffmpeg`
5. retry automatically with normalized WAVs
6. convert the successful result to OGG/Opus

### Helper script

For manual validation or operator use:

```bash
python3 scripts/styled_voice_request.py \
  --input '유빈아, 안녕? 나는 보라매 봇이야.' \
  --style-prompt 'soft, careful, slightly smiling' \
  --reference-audio /abs/path/sample1.ogg \
  --reference-audio /abs/path/sample2.m4a
```

The script prints JSON describing:

- input inspection results
- whether direct upload was attempted or skipped
- whether normalization fallback was used
- backend error summary if the request failed
- final WAV and OGG output paths on success

### Prompt-audio mode

Use prompt audio only if you have both:

- one clip that should act as `prompt_audio`
- the **exact transcript** of that clip

Otherwise, default to reference-only mode.

## Operational notes

- direct backend is used on purpose; nginx `/tts/...` was unhealthy during validation
- nginx/front-door health should be debugged separately from the skill contract itself
- `vllm` and `voxcpm` resource coexistence needs explicit operational checks; see `references/operations.md`
- if upstream Hermes changes around `gateway/run.py`, re-generate or refresh the patch in `patches/`

## Related docs

- `references/architecture.md`
- `references/operations.md`
- `references/v1.1-handoff.md`
