import wave
import stat

import pytest


def test_recorder_start_stop_creates_pcm_wav():
    from voxd.core.recorder import AudioRecorder

    recorder = AudioRecorder(samplerate=16000, channels=1, chunk_seconds=300)
    recorder.start_recording()
    output = recorder.stop_recording()

    assert output is not None and output.exists()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert stat.S_IMODE(output.parent.stat().st_mode) == 0o700
    with wave.open(str(output), "rb") as audio:
        assert audio.getframerate() == 16000
        assert audio.getnchannels() == 1
        assert audio.getnframes() > 0


def test_recorder_rotates_chunks_without_limiting_recording(monkeypatch):
    from voxd.core.recorder import AudioRecorder

    recorder = AudioRecorder(samplerate=16000, channels=1, chunk_seconds=300)
    recorder._chunk_target_frames = 1
    recorder.start_recording()

    assert recorder.is_recording is True
    assert len(recorder._chunk_paths) >= 2
    output = recorder.stop_recording()
    assert output is not None and output.exists()


def test_recorder_preserves_partial_audio_when_stream_stop_fails():
    from voxd.core.recorder import AudioRecorder

    recorder = AudioRecorder(samplerate=16000, channels=1)
    recorder.start_recording()
    recorder.stream.stop = lambda: (_ for _ in ()).throw(RuntimeError("device lost"))

    with pytest.raises(RuntimeError, match="partial recording preserved"):
        recorder.stop_recording()

    assert recorder.last_temp_file is not None
    assert recorder.last_temp_file.exists()
