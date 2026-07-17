from types import SimpleNamespace


def test_core_process_uses_gemma_and_types_final_text(monkeypatch, tmp_path):
    import voxd.core.clipboard as clipboard_module
    import voxd.core.gemma_transcriber as gemma_module
    import voxd.core.recorder as recorder_module
    import voxd.core.typer as typer_module
    from voxd.core.voxd_core import CoreProcessThread

    events = {
        "transcriber_kwargs": None,
        "typed": [],
        "copied": [],
        "logged": [],
        "finished": [],
    }
    recording_path = tmp_path / "recording.wav"

    class FakeRecorder:
        def start_recording(self):
            pass

        def stop_recording(self, preserve=False):
            assert preserve is False
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
            events["copied"].append(text)

    class FakeLogger:
        def log_entry(self, text):
            events["logged"].append(text)

    monkeypatch.setattr(recorder_module, "AudioRecorder", FakeRecorder)
    monkeypatch.setattr(gemma_module, "GemmaAudioTranscriber", FakeTranscriber)
    monkeypatch.setattr(typer_module, "SimulatedTyper", FakeTyper)
    monkeypatch.setattr(clipboard_module, "ClipboardManager", FakeClipboard)

    cfg = SimpleNamespace(
        data={
            "transcription_backend": "gemma",
            "gemma_server_url": "http://localhost:9292",
            "gemma_model": "gemma-e4b",
            "gemma_transcription_prompt": "Romanized Hindi",
            "gemma_segment_seconds": 25,
            "gemma_segment_overlap_seconds": 1,
            "gemma_timeout": 300,
            "gemma_max_tokens": 1024,
        },
        typing=True,
        typing_delay=2,
        typing_start_delay=0,
        aipp_enabled=True,
        perf_collect=False,
    )

    thread = CoreProcessThread(cfg, FakeLogger())
    thread.should_stop = True
    thread.finished.connect(events["finished"].append)
    thread.run()

    assert events["transcriber_kwargs"]["segment_seconds"] == 25
    assert events["typed"] == ["namaste doston"]
    assert events["copied"] == ["namaste doston"]
    assert events["logged"] == ["namaste doston"]
    assert events["finished"] == ["namaste doston"]


def test_core_process_rejects_unknown_transcription_backend(monkeypatch):
    import voxd.core.recorder as recorder_module
    from voxd.core.voxd_core import CoreProcessThread

    class FakeRecorder:
        pass

    monkeypatch.setattr(recorder_module, "AudioRecorder", FakeRecorder)
    cfg = SimpleNamespace(data={"transcription_backend": "gemmma"})
    finished = []

    thread = CoreProcessThread(cfg, logger=None)
    thread.finished.connect(finished.append)
    thread.run()

    assert finished == [""]
