# styled-voice architecture

## Why this repository exists

The goal is to keep `/styled-voice` out of the upstream Hermes repository while still supporting the one runtime behavior the skill needs: visibility into cached Discord audio attachment paths.

A pure external skill is not enough, because the model otherwise sees only transcribed audio content and not the local cache file paths required to upload reference audio to VoxCPM.

## Boundary

### Hermes upstream runtime

Hermes is responsible only for:

- receiving Discord attachments
- caching them locally
- exposing those cached paths to the model **only** when the request begins with `/styled-voice`

### External skill repo

This repository is responsible for:

- deciding how to treat the attached audio files
- normalizing odd Discord audio encodings
- calling the direct VoxCPM backend
- converting the generated result to Discord-friendly OGG/Opus
- documenting installation and verification

## Why patch instead of fork

A patch bundle has the right ergonomics here:

- upstream Hermes can stay upstream
- local runtime behavior can be reproduced exactly
- the feature-specific logic stays outside core
- the patch scope is tiny and reviewable

## Operational assumptions

- direct TTS endpoint: `http://10.40.40.40:9100/v1/audio/speech`
- Discord audio cache may contain misleading extensions/container metadata
- OGG/Opus is preferred for Discord playback
