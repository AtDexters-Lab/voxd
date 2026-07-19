import hashlib
import json
import subprocess
import wave
from pathlib import Path


def _write_wav(path: Path, *, duration_seconds: float = 0.1) -> None:
    frame_rate = 16_000
    frames = int(duration_seconds * frame_rate)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(frame_rate)
        output.writeframes(b"\x00\x00" * frames)


def test_archive_stores_private_flac_and_sidecar(monkeypatch, tmp_path):
    from voxd.core.archive import RecordingArchive

    source = tmp_path / "20260719_120000_000001_recording.wav"
    archive_dir = tmp_path / "archive"
    _write_wav(source)

    def fake_run(args, **kwargs):
        assert args[0] == "/usr/bin/ffmpeg"
        assert kwargs["check"] is True
        Path(args[-1]).write_bytes(b"fLaCtest")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("voxd.core.archive.subprocess.run", fake_run)
    archived = RecordingArchive(
        directory=archive_dir,
        ffmpeg_path="/usr/bin/ffmpeg",
    ).store(source, {"transcription": {"text": "namaste"}})

    sidecar = archive_dir / "20260719_120000_000001_recording.json"
    document = json.loads(sidecar.read_text(encoding="utf-8"))
    assert archived.name == "20260719_120000_000001_recording.flac"
    assert archived.read_bytes() == b"fLaCtest"
    assert not source.exists()
    assert archive_dir.stat().st_mode & 0o777 == 0o700
    assert archived.stat().st_mode & 0o777 == 0o600
    assert sidecar.stat().st_mode & 0o777 == 0o600
    assert document["schema_version"] == 1
    assert document["audio"]["codec"] == "flac"
    assert document["audio"]["sample_rate_hz"] == 16_000
    assert document["audio"]["channels"] == 1
    assert document["audio"]["duration_seconds"] == 0.1
    assert document["audio"]["sha256"] == hashlib.sha256(b"fLaCtest").hexdigest()
    assert document["transcription"]["text"] == "namaste"


def test_archive_retains_private_wav_when_flac_encoding_fails(monkeypatch, tmp_path):
    from voxd.core.archive import RecordingArchive

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "20260719_120000_000002_recording.wav"
    archive_dir = tmp_path / "archive"
    _write_wav(source)

    def fail_run(args, **kwargs):
        raise subprocess.CalledProcessError(1, args, stderr=b"encoder failed")

    monkeypatch.setattr("voxd.core.archive.subprocess.run", fail_run)
    archived = RecordingArchive(
        directory=archive_dir,
        ffmpeg_path="/usr/bin/ffmpeg",
    ).store(source, {"transcription": {"status": "failed"}})

    document = json.loads(archived.with_suffix(".json").read_text(encoding="utf-8"))
    assert archived.suffix == ".wav"
    assert archived.exists()
    assert not source.exists()
    assert archived.stat().st_mode & 0o777 == 0o600
    assert document["audio"]["codec"] == "pcm_s16le"
    assert "compression_error" in document["audio"]


def test_archive_quota_prunes_oldest_complete_bundle(monkeypatch, tmp_path):
    from voxd.core.archive import RecordingArchive

    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    old_audio = archive_dir / "20260718_120000_000001_recording.flac"
    old_sidecar = archive_dir / "20260718_120000_000001_recording.json"
    old_audio.write_bytes(b"o" * 20)
    old_sidecar.write_bytes(b"{}")
    source = tmp_path / "20260719_120000_000003_recording.wav"
    _write_wav(source)

    def fake_run(args, **kwargs):
        Path(args[-1]).write_bytes(b"n" * 20)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("voxd.core.archive.subprocess.run", fake_run)
    archived = RecordingArchive(
        directory=archive_dir,
        max_bytes=1,
        ffmpeg_path="/usr/bin/ffmpeg",
    ).store(source, {"transcription": {"text": "new"}})

    assert archived.exists()
    assert archived.with_suffix(".json").exists()
    assert not old_audio.exists()
    assert not old_sidecar.exists()
