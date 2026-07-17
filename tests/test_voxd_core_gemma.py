from types import SimpleNamespace


def _config():
    return SimpleNamespace(
        gemma_server_url="http://localhost:9292",
        gemma_model="gemma-e4b",
        gemma_segment_seconds=25,
        gemma_segment_overlap_seconds=1,
        gemma_timeout=300,
        gemma_max_tokens=1024,
        record_chunk_seconds=300,
        audio_input_device="",
        audio_prefer_pulse=True,
        typing_delay=2,
        typing_start_delay=0,
        data={"append_trailing_space": True},
    )


def _install_fakes(monkeypatch, tmp_path, *, clipboard_error=None):
    import voxd.core.clipboard as clipboard_module
    import voxd.core.recorder as recorder_module
    import voxd.core.typer as typer_module
    import voxd.core.voxd_core as core_module

    events = {"transcriber_kwargs": None, "typed": [], "copied": []}
    recording_path = tmp_path / "recording.wav"

    class FakeRecorder:
        def __init__(self, **kwargs):
            assert kwargs["chunk_seconds"] == 300
            self.is_recording = False

        def start_recording(self):
            self.is_recording = True

        def stop_recording(self, preserve=False):
            assert preserve is False
            self.is_recording = False
            return recording_path

    class FakeTranscriber:
        def __init__(self, **kwargs):
            events["transcriber_kwargs"] = kwargs

        def transcribe(self, path):
            assert path == recording_path
            return "namaste doston", ""

    class FakeTyper:
        def __init__(self, delay, start_delay, cfg):
            assert delay == 2
            assert start_delay == 0

        def type(self, text):
            events["typed"].append(text)

    class FakeClipboard:
        def copy(self, text):
            if clipboard_error:
                raise clipboard_error
            events["copied"].append(text)

    monkeypatch.setattr(recorder_module, "AudioRecorder", FakeRecorder)
    monkeypatch.setattr(core_module, "GemmaAudioTranscriber", FakeTranscriber)
    monkeypatch.setattr(typer_module, "YdotoolTyper", FakeTyper)
    monkeypatch.setattr(clipboard_module, "ClipboardManager", FakeClipboard)
    return events


def test_core_process_uses_gemma_and_types_final_text(monkeypatch, tmp_path):
    from voxd.core.voxd_core import CoreProcessThread

    events = _install_fakes(monkeypatch, tmp_path)
    finished = []
    thread = CoreProcessThread(_config())
    thread.should_stop = True
    thread.finished.connect(finished.append)
    thread.run()

    assert events["transcriber_kwargs"]["segment_seconds"] == 25
    assert events["typed"] == ["namaste doston"]
    assert events["copied"] == ["namaste doston"]
    assert finished == ["namaste doston"]


def test_clipboard_failure_does_not_block_real_typing(monkeypatch, tmp_path):
    from voxd.core.voxd_core import CoreProcessThread

    events = _install_fakes(monkeypatch, tmp_path, clipboard_error=RuntimeError("no clipboard"))
    finished = []
    thread = CoreProcessThread(_config())
    thread.should_stop = True
    thread.finished.connect(finished.append)
    thread.run()

    assert events["typed"] == ["namaste doston"]
    assert finished == ["namaste doston"]
