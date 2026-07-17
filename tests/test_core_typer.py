import pytest


def test_detect_backend_env(monkeypatch):
    from voxd.core.typer import detect_backend
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert detect_backend() == "wayland"


def test_typer_paste_path(monkeypatch):
    from voxd.core.typer import SimulatedTyper
    # Disable tools so it falls back to paste
    monkeypatch.setenv("WAYLAND_DISPLAY", "")
    monkeypatch.setenv("DISPLAY", "")
    t = SimulatedTyper(delay=0, start_delay=0)
    # Emulate no tool available
    t.tool = None
    # Should not raise
    t.type("hello")


def _make_ydotool_typer():
    from voxd.core.typer import SimulatedTyper

    typer = object.__new__(SimulatedTyper)
    typer.enabled = True
    typer.tool = "/usr/bin/ydotool"
    typer.delay_ms = 2.0
    typer.delay_str = "2"
    typer.start_delay = 0.0
    typer.cfg = type("Cfg", (), {"data": {"append_trailing_space": True}})()
    return typer


def test_ydotool_types_long_text_as_real_keystroke_chunks(monkeypatch):
    typer = _make_ydotool_typer()
    calls = []

    class Result:
        returncode = 0

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("timeout")))
        return Result()

    monkeypatch.setattr("voxd.core.typer.subprocess.run", fake_run)
    monkeypatch.setattr("voxd.core.typer.time.sleep", lambda *_: None)

    text = ("namaste duniya this is a long Hinglish transcript " * 30).strip()
    typer.type(text)

    type_calls = [(cmd, timeout) for cmd, timeout in calls if len(cmd) > 1 and cmd[1] == "type"]
    assert len(type_calls) > 1
    assert "".join(cmd[-1] for cmd, _ in type_calls) == text + " "
    assert all(len(cmd[-1]) <= 400 for cmd, _ in type_calls)
    assert all("-H" in cmd and cmd[cmd.index("-H") + 1] == "5" for cmd, _ in type_calls)
    assert all(timeout >= 5 for _, timeout in type_calls)
    assert max(timeout for _, timeout in type_calls) > 8


def test_ydotool_chunk_limit_includes_boundary_whitespace():
    from voxd.core.typer import SimulatedTyper

    text = "a" * 400 + " " + "tail"
    chunks = list(SimulatedTyper._split_typing_chunks(text, max_chars=400))

    assert "".join(chunks) == text
    assert all(len(chunk) <= 400 for chunk in chunks)


def test_ydotool_stops_after_failed_chunk(monkeypatch):
    typer = _make_ydotool_typer()
    attempts = []

    def fake_run_tool(cmd, *, timeout=10):
        attempts.append(cmd[-1])
        return len(attempts) == 1

    monkeypatch.setattr(typer, "_run_tool", fake_run_tool)
    monkeypatch.setattr(typer, "_release_all_keys_ydotool", lambda: None)
    monkeypatch.setattr("voxd.core.typer.time.sleep", lambda *_: None)

    with pytest.raises(RuntimeError, match="complete transcript"):
        typer.type("word " * 300)

    assert len(attempts) == 2
