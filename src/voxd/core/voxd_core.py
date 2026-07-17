from __future__ import annotations

from threading import Thread

from PyQt6.QtCore import QThread, pyqtSignal

from voxd.core.gemma_transcriber import GemmaAudioTranscriber


class CoreProcessThread(QThread):
    """Own one record, transcribe, copy, and type cycle."""

    finished = pyqtSignal(str)
    status_changed = pyqtSignal(str)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.should_stop = False

    def stop_recording(self) -> None:
        self.should_stop = True

    def run(self) -> None:
        from voxd.core.clipboard import ClipboardManager
        from voxd.core.recorder import AudioRecorder
        from voxd.core.typer import YdotoolTyper

        transcript = ""
        recorder = None
        try:
            transcriber = GemmaAudioTranscriber(
                server_url=self.cfg.gemma_server_url,
                model=self.cfg.gemma_model,
                segment_seconds=self.cfg.gemma_segment_seconds,
                overlap_seconds=self.cfg.gemma_segment_overlap_seconds,
                timeout=self.cfg.gemma_timeout,
                max_tokens=self.cfg.gemma_max_tokens,
            )
            recorder = AudioRecorder(
                chunk_seconds=self.cfg.record_chunk_seconds,
                input_device=self.cfg.audio_input_device,
                prefer_pulse=self.cfg.audio_prefer_pulse,
            )
            recorder.start_recording()
            warmup_thread = Thread(
                target=self._warmup_model,
                args=(transcriber,),
                name="voxd-gemma-warmup",
                daemon=True,
            )
            warmup_thread.start()
            while not self.should_stop:
                self.msleep(100)

            self.status_changed.emit("Transcribing")
            recording_path = recorder.stop_recording()
            if recording_path is None:
                raise RuntimeError("recorder produced no audio file")
            warmup_thread.join()
            transcript, _ = transcriber.transcribe(recording_path)
            if not transcript:
                raise RuntimeError("E4B returned an empty transcript")

            # Clipboard is recovery state only; the normal insertion path is
            # always genuine ydotool input events.
            clipboard_ready = False
            try:
                ClipboardManager().copy(transcript)
                clipboard_ready = True
            except Exception as exc:
                # Clipboard is a fallback, not a prerequisite for real typing.
                print(f"[core] Could not copy recovery text: {exc}", flush=True)

            self.status_changed.emit("Typing")
            try:
                YdotoolTyper(
                    delay=self.cfg.typing_delay,
                    start_delay=self.cfg.typing_start_delay,
                    cfg=self.cfg,
                ).type(transcript)
            except Exception as exc:
                recovery = (
                    "full transcript remains on clipboard"
                    if clipboard_ready
                    else "clipboard recovery was also unavailable"
                )
                print(f"[core] Typing failed; {recovery}: {exc}", flush=True)
        except Exception as exc:
            print(f"[core] Dictation failed: {exc}", flush=True)
            if recorder is not None and recorder.is_recording:
                try:
                    recorder.stop_recording(preserve=True)
                except Exception:
                    pass
            transcript = ""
        finally:
            self.finished.emit(transcript)

    @staticmethod
    def _warmup_model(transcriber) -> None:
        try:
            transcriber.warmup()
        except Exception as exc:
            print(
                f"[core] Model warmup failed; continuing with normal transcription: {exc}",
                flush=True,
            )
