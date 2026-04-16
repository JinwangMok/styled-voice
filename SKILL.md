---
name: styled-voice
description: Create speech in the user's style by sending attached audio samples to the direct VoxCPM backend at 10.40.40.40:9100. Trigger via /styled-voice in Discord.
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [voice-cloning, tts, voxcpm, discord, audio]
---

# /styled-voice

Use this skill when the user invokes `/styled-voice` and has attached one or more audio samples in Discord.

## Goal

Generate new audio in the user's voice/style by sending cached local audio attachments to the **direct VoxCPM backend**:

- **Endpoint:** `http://10.40.40.40:9100/v1/audio/speech`
- **Do not use nginx `/tts/...` routes** for this skill.

## Runtime contract

This external skill expects a tiny Hermes runtime patch to be installed. The patch is shipped with this repository in `patches/hermes-gateway-styled-voice.patch` and only does one thing:

- for `/styled-voice` requests, expose cached local audio attachment paths to the model as text lines.

After the patch is applied, Hermes injects local cached audio paths into the user-visible message as lines like:

- `[Audio attachment saved at: /abs/path/sample1.wav]`
- `[Audio attachment saved at: /abs/path/sample2.m4a]`

These are the exact files to upload with curl or with the helper script in this repository.

The normal STT enrichment may also be present, but the **cached file paths are the source of truth** for building the multipart request.

## Default behavior

Unless the user clearly specifies otherwise:

1. Treat **all attached audio files as `reference_audio`**.
2. Use the text after `/styled-voice` as the target text to synthesize.
3. If the user also provides a style phrase (for example `차분하고 부드럽게, 살짝 웃는 느낌으로`), pass it as `style_prompt`.
4. Request `response_format=wav` from VoxCPM.
5. Save the result to a local temp/output `.wav` file.
6. Convert the final audio to OGG/Opus for Discord playback when replying.
7. Return it with `MEDIA:/absolute/path/to/output.ogg`.

## Concise user-facing guidance

If the user seems unsure, steer them toward this simple form:

```text
1) Attach 1-3 short voice samples
2) Write: /styled-voice 생성할 문장
3) Optionally add a style phrase like “차분하고 부드럽게” or “soft, whispery, with small pauses”
```

Recommended sample quality:

- 3-15 seconds each
- single speaker
- minimal music/noise
- cleaner clips matter more than more clips

## Style phrasing cheat sheet

If the user asks how to request a stronger style, suggest phrases like these.

### hesitation / pauses
- `살짝 망설이듯`
- `조금 생각하면서 천천히`
- `with small pauses, slightly hesitant`

### slower pacing
- `조금 느리게`
- `또박또박, 급하지 않게`
- `slow, measured, unhurried`

### softness / warmth
- `부드럽고 다정하게`
- `차분하고 조심스럽게`
- `soft, warm, gentle`

### whisperiness / breathiness
- `작게 속삭이듯`
- `숨결이 조금 섞인 느낌으로`
- `soft whispery tone`

### brighter / smiling
- `살짝 웃는 느낌으로`
- `밝고 편안하게`
- `slightly smiling, conversational`

If the user provides no style guidance, do not overcomplicate it. Use a light neutral style prompt only when clearly helpful.

## Optional prompt-audio mode

If the user explicitly provides:

- one audio to use as **prompt audio**, and
- the **exact transcript** for that prompt audio,

then send:

- `prompt_audio=@...`
- `prompt_text=...`

and use the remaining clips as `reference_audio`.

If the user does **not** provide an exact transcript, do **not** guess one from STT for prompt mode unless they explicitly ask you to use the transcript as-is. Default back to reference-only mode.

## Required checks

Before calling the backend:

1. Extract all injected audio-path lines.
2. Verify each file exists.
3. If no attached audio files are available, tell the user to attach 1-3 sample audios and try again.
4. If the synthesis text is empty, ask the user what sentence to generate.

## Preferred robust execution path

Use this retry strategy unless the user explicitly asks you to do something different:

1. Inspect the extracted files with `ffprobe`.
2. Decide whether direct upload looks safe.
3. If safe, try direct upload first.
4. If the backend fails, returns non-audio, or the media looks suspicious, normalize inputs to mono WAV with `ffmpeg`.
5. Retry automatically with normalized WAVs.
6. Convert the successful output to OGG/Opus.
7. Return the OGG file.

Discord-cached audio may arrive with misleading extensions/containers (for example `.ogg` files that actually contain AAC). Treat suspicious container/codec mismatches as a reason to normalize.

## Preferred helper command

If this repository is available locally, prefer the bundled helper script because it already implements the direct → normalize-retry → OGG flow and gives clearer error summaries.

Example:

```bash
python3 scripts/styled_voice_request.py \
  --input '생성할 문장' \
  --style-prompt 'soft, careful, slightly smiling' \
  --reference-audio /abs/path/sample1.ogg \
  --reference-audio /abs/path/sample2.m4a
```

It will:

- inspect inputs
- optionally skip unsafe direct upload
- retry automatically with normalized WAVs
- emit JSON with the chosen strategy and any backend failure summary
- produce both `.wav` and final `.ogg`

## Exact request pattern if you do it manually

Use the `terminal` tool with `curl -F ...` multipart form upload.

### Normalization flow

```bash
ffprobe /abs/path/sample1.ogg
ffmpeg -y -i /abs/path/sample1.ogg -ac 1 -ar 48000 /tmp/sample1.wav
ffmpeg -y -i /abs/path/sample2.ogg -ac 1 -ar 48000 /tmp/sample2.wav
```

### Reference-only example

```bash
curl -sS -X POST http://10.40.40.40:9100/v1/audio/speech \
  -o /tmp/styled-voice-output.wav \
  -F model=voxcpm2 \
  -F 'input=생성할 문장' \
  -F 'style_prompt=calm, slightly smiling, conversational' \
  -F response_format=wav \
  -F reference_audio=@/abs/path/sample1.wav \
  -F reference_audio=@/abs/path/sample2.m4a
```

### Prompt-audio + transcript example

```bash
curl -sS -X POST http://10.40.40.40:9100/v1/audio/speech \
  -o /tmp/styled-voice-output.wav \
  -F model=voxcpm2 \
  -F 'input=생성할 문장' \
  -F 'style_prompt=calm, slightly smiling, conversational' \
  -F response_format=wav \
  -F reference_audio=@/abs/path/ref1.wav \
  -F prompt_audio=@/abs/path/prompt.wav \
  -F 'prompt_text=프롬프트 오디오의 정확한 전사 텍스트'
```

## Output handling

After synthesis succeeds:

1. Verify the output file exists and is non-empty.
2. Convert to OGG/Opus for Discord playback:

```bash
ffmpeg -y -i /tmp/styled-voice-output.wav -c:a libopus -b:a 96k /tmp/styled-voice-output.ogg
```

3. Respond briefly and include:

```text
MEDIA:/absolute/path/to/output.ogg
```

## Failure handling

- If curl returns non-200 or the output is not a valid audio payload, summarize the backend error clearly.
- If the backend is unavailable, tell the user the direct VoxCPM backend at `10.40.40.40:9100` is not responding.
- If multiple audio files are attached and the user does not specify roles, use **reference-only mode** with all of them.
- If the user asks for “my voice style” and provides samples only, that is sufficient for reference-only mode.
- Do not mention nginx routes in the reply unless the user explicitly asks about operational issues.

## Response style

Be operational and concise:

- say what assumption you made about the uploaded files
- mention if you normalized/retried
- generate the audio
- return the file
