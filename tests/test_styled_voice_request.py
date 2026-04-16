import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "styled_voice_request.py"
spec = importlib.util.spec_from_file_location("styled_voice_request", MODULE_PATH)
styled_voice_request = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = styled_voice_request
spec.loader.exec_module(styled_voice_request)


class TestHeuristics:
    def test_should_skip_direct_upload_for_suspicious_container_codec_mismatch(self):
        probe = {
            "format": {"format_name": "ogg"},
            "streams": [{"codec_type": "audio", "codec_name": "aac"}],
        }

        decision = styled_voice_request.classify_audio_path(Path("sample.ogg"), probe)

        assert decision.should_try_direct is False
        assert "codec mismatch" in decision.reason

    def test_should_allow_direct_upload_for_expected_wav(self):
        probe = {
            "format": {"format_name": "wav"},
            "streams": [{"codec_type": "audio", "codec_name": "pcm_s16le"}],
        }

        decision = styled_voice_request.classify_audio_path(Path("sample.wav"), probe)

        assert decision.should_try_direct is True
        assert decision.reason == "direct upload looks safe"


class TestBackendErrorSummary:
    def test_prefers_json_detail_message(self):
        summary = styled_voice_request.summarize_backend_error(
            status_code=500,
            body_bytes=b'{"detail":"decoder failed"}',
            content_type="application/json",
        )

        assert "decoder failed" in summary
        assert "HTTP 500" in summary

    def test_falls_back_to_trimmed_plain_text(self):
        summary = styled_voice_request.summarize_backend_error(
            status_code=502,
            body_bytes=b'bad gateway from nginx upstream' + b'!' * 400,
            content_type="text/plain",
        )

        assert summary.startswith("HTTP 502")
        assert len(summary) < 260


class TestMultipartArgs:
    def test_build_form_args_repeats_reference_audio_and_prompt_audio_fields(self, tmp_path):
        ref1 = tmp_path / "ref1.wav"
        ref2 = tmp_path / "ref2.wav"
        prompt = tmp_path / "prompt.wav"
        for path in (ref1, ref2, prompt):
            path.write_bytes(b"RIFF")

        args = styled_voice_request.build_form_args(
            input_text="hello",
            style_prompt="soft and careful",
            response_format="wav",
            reference_audio_paths=[ref1, ref2],
            prompt_audio_path=prompt,
            prompt_text="exact transcript",
            model="voxcpm2",
        )

        assert args.count("-F") == 8
        assert "reference_audio=@{}".format(ref1) in args
        assert "reference_audio=@{}".format(ref2) in args
        assert "prompt_audio=@{}".format(prompt) in args
        assert "prompt_text=exact transcript" in args


class TestMainFlow:
    def test_main_returns_direct_strategy_without_normalization_when_inputs_look_safe(self, monkeypatch, tmp_path, capsys):
        ref = tmp_path / "ref.wav"
        ref.write_bytes(b"RIFF")
        wav_output = tmp_path / "result.wav"
        ogg_output = tmp_path / "result.ogg"

        monkeypatch.setattr(styled_voice_request, "ensure_dependencies", lambda: None)
        monkeypatch.setattr(styled_voice_request, "ffprobe_json", lambda path: {"format": {"format_name": "wav"}, "streams": [{"codec_type": "audio", "codec_name": "pcm_s16le"}]})

        def fake_run_curl_attempt(**kwargs):
            kwargs["output_path"].write_bytes(b"RIFF")
            return styled_voice_request.CurlResult(True, 200, "audio/wav", kwargs["output_path"], "direct upload succeeded", kwargs["attempt"])

        monkeypatch.setattr(styled_voice_request, "run_curl_attempt", fake_run_curl_attempt)
        monkeypatch.setattr(styled_voice_request, "normalize_audio", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("normalize_audio should not be called")))
        monkeypatch.setattr(styled_voice_request, "convert_to_ogg", lambda input_path, output_path: output_path.write_bytes(b"OggS") or output_path)

        exit_code = styled_voice_request.main([
            "--input", "hello",
            "--reference-audio", str(ref),
            "--output-dir", str(tmp_path),
            "--output-name", "result",
        ])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert wav_output.exists()
        assert ogg_output.exists()
        assert '"strategy": "direct"' in captured.out

    def test_main_retries_with_normalized_audio_when_direct_upload_is_skipped(self, monkeypatch, tmp_path, capsys):
        suspicious = tmp_path / "sample.ogg"
        suspicious.write_bytes(b"OggS")
        normalized_calls = []

        monkeypatch.setattr(styled_voice_request, "ensure_dependencies", lambda: None)
        monkeypatch.setattr(styled_voice_request, "ffprobe_json", lambda path: {"format": {"format_name": "ogg"}, "streams": [{"codec_type": "audio", "codec_name": "aac"}]})

        def fake_normalize_audio(input_path, output_path):
            normalized_calls.append((input_path, output_path))
            output_path.write_bytes(b"RIFF")
            return output_path

        def fake_run_curl_attempt(**kwargs):
            assert kwargs["attempt"] == "normalized"
            assert all(path.suffix == ".wav" for path in kwargs["reference_audio_paths"])
            kwargs["output_path"].write_bytes(b"RIFF")
            return styled_voice_request.CurlResult(True, 200, "audio/wav", kwargs["output_path"], "normalized upload succeeded", kwargs["attempt"])

        monkeypatch.setattr(styled_voice_request, "normalize_audio", fake_normalize_audio)
        monkeypatch.setattr(styled_voice_request, "run_curl_attempt", fake_run_curl_attempt)
        monkeypatch.setattr(styled_voice_request, "convert_to_ogg", lambda input_path, output_path: output_path.write_bytes(b"OggS") or output_path)

        exit_code = styled_voice_request.main([
            "--input", "hello",
            "--reference-audio", str(suspicious),
            "--output-dir", str(tmp_path),
            "--output-name", "result",
        ])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert len(normalized_calls) == 1
        assert '"strategy": "normalized-retry"' in captured.out
        assert '"attempt": "direct-skipped"' in captured.out

    def test_main_surfaces_ffprobe_failures_as_json_error(self, monkeypatch, tmp_path, capsys):
        ref = tmp_path / "broken.wav"
        ref.write_bytes(b"not-audio")

        monkeypatch.setattr(styled_voice_request, "ensure_dependencies", lambda: None)

        def boom(_path):
            raise RuntimeError("ffprobe exploded")

        monkeypatch.setattr(styled_voice_request, "ffprobe_json", boom)

        exit_code = styled_voice_request.main([
            "--input", "hello",
            "--reference-audio", str(ref),
            "--output-dir", str(tmp_path),
            "--output-name", "result",
        ])

        captured = capsys.readouterr()
        assert exit_code == 1
        assert 'ffprobe exploded' in captured.out
        assert '"ok": false' in captured.out
