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

These are the exact files to upload with curl.

The normal STT enrichment may also be present, but the **cached file paths are the source of truth** for building the multipart request.

Important runtime finding: Discord-cached audio may arrive with misleading extensions/containers (for example `.ogg` files that actually contain AAC). If the direct VoxCPM backend returns 500 on the raw cached files, normalize them locally with `ffmpeg` to mono WAV first, then upload the normalized `.wav` files instead.

## Default behavior

Unless the user clearly specifies otherwise:

1. Treat **all attached audio files as `reference_audio`**.
2. Use the text after `/styled-voice` as the target text to synthesize.
3. If the user also provides a style phrase (e.g. “cheerful, calm, slightly smiling”), pass it as `style_prompt`.
4. Request `response_format=wav` from VoxCPM.
5. Save the result to a local temp/output `.wav` file.
6. Convert the final audio to OGG/Opus for Discord playback when replying.
7. Return it with `MEDIA:/absolute/path/to/output.ogg`.

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

## Exact request pattern

Use the `terminal` tool with `curl -F ...` multipart form upload.

### If the cached attachments fail directly

If the backend returns a 500 when uploading cached Discord audio paths, inspect the files with `ffprobe` and normalize them locally before retrying. This is important because the cache may contain AAC-in-OGG or other mismatched container/codec combinations.

Example normalization flow:

```bash
ffprobe /abs/path/sample1.ogg
ffmpeg -y -i /abs/path/sample1.ogg -ac 1 -ar 48000 /tmp/sample1.wav
ffmpeg -y -i /abs/path/sample2.ogg -ac 1 -ar 48000 /tmp/sample2.wav
```

Then use the normalized WAVs as `reference_audio` / `prompt_audio` in the multipart request.

### Reference-only example

```bash
curl -sS -X POST http://10.40.40.40:9100/v1/audio/speech   -o /tmp/styled-voice-output.wav   -F model=voxcpm2   -F 'input=생성할 문장'   -F 'style_prompt=calm, slightly smiling, conversational'   -F response_format=wav   -F reference_audio=@/abs/path/sample1.wav   -F reference_audio=@/abs/path/sample2.m4a
```

### Prompt-audio + transcript example

```bash
curl -sS -X POST http://10.40.40.40:9100/v1/audio/speech   -o /tmp/styled-voice-output.wav   -F model=voxcpm2   -F 'input=생성할 문장'   -F 'style_prompt=calm, slightly smiling, conversational'   -F response_format=wav   -F reference_audio=@/abs/path/ref1.wav   -F prompt_audio=@/abs/path/prompt.wav   -F 'prompt_text=프롬프트 오디오의 정확한 전사 텍스트'
```

## Output handling

After curl succeeds:

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

- If curl returns non-200 or the output is not a WAV/audio payload, summarize the backend error.
- If the backend is unavailable, tell the user the direct VoxCPM backend at `10.40.40.40:9100` is not responding.
- If multiple audio files are attached and the user does not specify roles, use **reference-only mode** with all of them.
- If the user asks for “my voice style” and provides samples only, that is sufficient for reference-only mode.

## Response style

Be operational and concise:

- say what assumption you made about the uploaded files
- generate the audio
- return the file

Do not mention nginx routes. Use the direct backend only.
