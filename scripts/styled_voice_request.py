#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

DEFAULT_ENDPOINT = "http://10.40.40.40:9100/v1/audio/speech"
DEFAULT_MODEL = "voxcpm2"
DEFAULT_OUTPUT_NAME = "styled-voice-output"
DEFAULT_RESPONSE_FORMAT = "wav"

EXPECTED_FORMAT_HINTS = {
    ".wav": {"wav", "wave"},
    ".ogg": {"ogg"},
    ".oga": {"ogg"},
    ".opus": {"ogg"},
    ".m4a": {"mov", "mp4", "ipod", "m4a"},
    ".mp3": {"mp3"},
    ".flac": {"flac"},
}
EXPECTED_CODECS = {
    ".wav": {"pcm_s16le", "pcm_s24le", "pcm_f32le", "pcm_f64le", "pcm_u8"},
    ".ogg": {"vorbis", "opus", "flac"},
    ".oga": {"vorbis", "opus", "flac"},
    ".opus": {"opus"},
    ".m4a": {"aac", "alac", "mp3"},
    ".mp3": {"mp3"},
    ".flac": {"flac"},
}


@dataclass
class AudioDecision:
    should_try_direct: bool
    reason: str
    extension: str
    format_name: str
    codec_name: str


@dataclass
class CurlResult:
    success: bool
    status_code: int
    content_type: str
    output_path: Path
    summary: str
    attempt: str


def run_command(command: Sequence[str], *, capture_output: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, capture_output=capture_output, text=False)


def ffprobe_json(path: Path) -> dict:
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    return json.loads(result.stdout.decode("utf-8"))


def classify_audio_path(path: Path, probe: dict) -> AudioDecision:
    ext = path.suffix.lower()
    format_name = ((probe.get("format") or {}).get("format_name") or "").lower()
    stream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), {})
    codec_name = (stream.get("codec_name") or "").lower()

    expected_formats = EXPECTED_FORMAT_HINTS.get(ext, set())
    expected_codecs = EXPECTED_CODECS.get(ext, set())

    format_ok = not expected_formats or any(token in format_name.split(",") for token in expected_formats)
    codec_ok = not expected_codecs or codec_name in expected_codecs

    if format_ok and codec_ok:
        return AudioDecision(True, "direct upload looks safe", ext, format_name, codec_name)

    problems = []
    if not format_ok:
        problems.append(f"format mismatch: .{ext.lstrip('.')} vs {format_name or 'unknown'}")
    if not codec_ok:
        problems.append(f"codec mismatch: .{ext.lstrip('.')} vs {codec_name or 'unknown'}")
    return AudioDecision(False, "; ".join(problems), ext, format_name, codec_name)


def summarize_backend_error(*, status_code: int, body_bytes: bytes, content_type: str) -> str:
    summary = None
    if "json" in (content_type or ""):
        try:
            payload = json.loads(body_bytes.decode("utf-8", errors="replace"))
            if isinstance(payload, dict):
                summary = payload.get("detail") or payload.get("error") or payload.get("message")
                if not summary:
                    summary = json.dumps(payload, ensure_ascii=False)
            else:
                summary = json.dumps(payload, ensure_ascii=False)
        except Exception:
            summary = None
    if not summary:
        summary = body_bytes.decode("utf-8", errors="replace").strip() or "empty response body"
    summary = " ".join(summary.split())
    summary = summary[:220]
    return f"HTTP {status_code}: {summary}"


def build_form_args(
    *,
    input_text: str,
    style_prompt: str | None,
    response_format: str,
    reference_audio_paths: Sequence[Path],
    prompt_audio_path: Path | None,
    prompt_text: str | None,
    model: str,
) -> list[str]:
    args = [
        "-F",
        f"model={model}",
        "-F",
        f"input={input_text}",
        "-F",
        f"response_format={response_format}",
    ]
    if style_prompt:
        args += ["-F", f"style_prompt={style_prompt}"]
    for path in reference_audio_paths:
        args += ["-F", f"reference_audio=@{path}"]
    if prompt_audio_path:
        args += ["-F", f"prompt_audio=@{prompt_audio_path}"]
    if prompt_text:
        args += ["-F", f"prompt_text={prompt_text}"]
    return args


def audio_file_is_valid(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        ffprobe_json(path)
        return True
    except Exception:
        return False


def run_curl_attempt(
    *,
    endpoint: str,
    output_path: Path,
    input_text: str,
    style_prompt: str | None,
    response_format: str,
    reference_audio_paths: Sequence[Path],
    prompt_audio_path: Path | None,
    prompt_text: str | None,
    model: str,
    attempt: str,
) -> CurlResult:
    headers_path = output_path.with_suffix(output_path.suffix + f".{attempt}.headers")
    body_path = output_path.with_suffix(output_path.suffix + f".{attempt}.body")
    cmd = [
        "curl",
        "-sS",
        "-X",
        "POST",
        endpoint,
        "-D",
        str(headers_path),
        "-o",
        str(body_path),
        "-w",
        "%{http_code}",
        *build_form_args(
            input_text=input_text,
            style_prompt=style_prompt,
            response_format=response_format,
            reference_audio_paths=reference_audio_paths,
            prompt_audio_path=prompt_audio_path,
            prompt_text=prompt_text,
            model=model,
        ),
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return CurlResult(False, 0, "", body_path, f"curl failed: {result.stderr.strip()}", attempt)

    status_code = int((result.stdout or "0").strip() or "0")
    content_type = ""
    if headers_path.exists():
        for line in headers_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("content-type:"):
                content_type = line.split(":", 1)[1].strip().lower()
    body_bytes = body_path.read_bytes() if body_path.exists() else b""

    if status_code != 200:
        return CurlResult(False, status_code, content_type, body_path, summarize_backend_error(status_code=status_code, body_bytes=body_bytes, content_type=content_type), attempt)

    guessed_content_type = content_type or (mimetypes.guess_type(str(body_path))[0] or "")
    if "audio" not in guessed_content_type and not audio_file_is_valid(body_path):
        return CurlResult(False, status_code, content_type, body_path, summarize_backend_error(status_code=status_code, body_bytes=body_bytes, content_type=content_type), attempt)

    if not audio_file_is_valid(body_path):
        return CurlResult(False, status_code, content_type, body_path, summarize_backend_error(status_code=status_code, body_bytes=body_bytes, content_type=content_type), attempt)

    body_path.replace(output_path)
    return CurlResult(True, status_code, content_type, output_path, f"{attempt} upload succeeded", attempt)


def normalize_audio(input_path: Path, output_path: Path) -> Path:
    run_command(["ffmpeg", "-y", "-i", str(input_path), "-ac", "1", "-ar", "48000", str(output_path)])
    return output_path


def convert_to_ogg(input_path: Path, output_path: Path) -> Path:
    run_command(["ffmpeg", "-y", "-i", str(input_path), "-c:a", "libopus", "-b:a", "96k", str(output_path)])
    return output_path


def ensure_dependencies() -> None:
    for cmd in ("curl", "ffprobe", "ffmpeg"):
        if not shutil.which(cmd):
            raise SystemExit(f"Required command not found: {cmd}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Try direct VoxCPM upload, auto-normalize suspicious/failed Discord audio, and always emit OGG/Opus.")
    parser.add_argument("--input", required=True, help="Target synthesis text")
    parser.add_argument("--style-prompt", help="Optional style prompt")
    parser.add_argument("--reference-audio", action="append", default=[], help="Reference audio path (repeatable)")
    parser.add_argument("--prompt-audio", help="Optional prompt audio path")
    parser.add_argument("--prompt-text", help="Exact transcript for prompt audio")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--output-name", default=DEFAULT_OUTPUT_NAME)
    parser.add_argument("--keep-temp", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    ensure_dependencies()

    input_text = args.input.strip()
    if not input_text:
        raise SystemExit("--input must not be empty")

    reference_audio_paths = [Path(p).expanduser().resolve() for p in args.reference_audio]
    if not reference_audio_paths:
        raise SystemExit("Provide at least one --reference-audio")

    prompt_audio_path = Path(args.prompt_audio).expanduser().resolve() if args.prompt_audio else None
    if prompt_audio_path and not args.prompt_text:
        raise SystemExit("--prompt-text is required when --prompt-audio is provided")

    for path in [*reference_audio_paths, *([prompt_audio_path] if prompt_audio_path else [])]:
        if not path.exists():
            raise SystemExit(f"Audio file not found: {path}")

    temp_root = Path(args.output_dir).expanduser().resolve() if args.output_dir else Path(tempfile.mkdtemp(prefix="styled-voice-"))
    temp_root.mkdir(parents=True, exist_ok=True)
    if args.output_dir:
        work_dir = temp_root
    else:
        work_dir = temp_root / "work"
        work_dir.mkdir(parents=True, exist_ok=True)

    inspections = []
    try:
        direct_ok = True
        try:
            for path in [*reference_audio_paths, *([prompt_audio_path] if prompt_audio_path else [])]:
                probe = ffprobe_json(path)
                decision = classify_audio_path(path, probe)
                inspections.append({"path": str(path), **asdict(decision)})
                if not decision.should_try_direct:
                    direct_ok = False
        except Exception as exc:
            print(json.dumps({
                "ok": False,
                "inspections": inspections,
                "attempts": [],
                "error": f"input inspection failed: {exc}",
            }, ensure_ascii=False, indent=2, default=str))
            return 1

        wav_output = temp_root / f"{args.output_name}.wav"
        ogg_output = temp_root / f"{args.output_name}.ogg"
        attempts = []

        if direct_ok:
            direct_result = run_curl_attempt(
                endpoint=args.endpoint,
                output_path=wav_output,
                input_text=input_text,
                style_prompt=args.style_prompt,
                response_format=DEFAULT_RESPONSE_FORMAT,
                reference_audio_paths=reference_audio_paths,
                prompt_audio_path=prompt_audio_path,
                prompt_text=args.prompt_text,
                model=args.model,
                attempt="direct",
            )
            attempts.append(asdict(direct_result))
            if direct_result.success:
                convert_to_ogg(wav_output, ogg_output)
                print(json.dumps({
                    "ok": True,
                    "strategy": "direct",
                    "inspections": inspections,
                    "attempts": attempts,
                    "wav_output": str(wav_output),
                    "ogg_output": str(ogg_output),
                }, ensure_ascii=False, indent=2, default=str))
                return 0
        else:
            attempts.append({"success": False, "status_code": 0, "content_type": "", "output_path": "", "summary": "skipped direct upload because at least one file looked suspicious", "attempt": "direct-skipped"})

        normalized_dir = work_dir / "normalized"
        normalized_dir.mkdir(parents=True, exist_ok=True)
        normalized_refs = [normalize_audio(path, normalized_dir / f"ref-{index:02d}.wav") for index, path in enumerate(reference_audio_paths, start=1)]
        normalized_prompt = normalize_audio(prompt_audio_path, normalized_dir / "prompt.wav") if prompt_audio_path else None

        retry_result = run_curl_attempt(
            endpoint=args.endpoint,
            output_path=wav_output,
            input_text=input_text,
            style_prompt=args.style_prompt,
            response_format=DEFAULT_RESPONSE_FORMAT,
            reference_audio_paths=normalized_refs,
            prompt_audio_path=normalized_prompt,
            prompt_text=args.prompt_text,
            model=args.model,
            attempt="normalized",
        )
        attempts.append(asdict(retry_result))
        if not retry_result.success:
            print(json.dumps({
                "ok": False,
                "inspections": inspections,
                "attempts": attempts,
                "error": retry_result.summary,
            }, ensure_ascii=False, indent=2, default=str))
            return 1

        convert_to_ogg(wav_output, ogg_output)
        print(json.dumps({
            "ok": True,
            "strategy": "normalized-retry",
            "inspections": inspections,
            "attempts": attempts,
            "wav_output": str(wav_output),
            "ogg_output": str(ogg_output),
        }, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        if not args.keep_temp and not args.output_dir:
            # keep the top-level temp dir because it contains final outputs; only remove the work subdir
            if work_dir.exists() and work_dir.name == "work":
                shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
