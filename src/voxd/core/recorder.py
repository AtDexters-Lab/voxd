from __future__ import annotations

import wave
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd

from voxd.paths import DATA_DIR, RECORDINGS_DIR
from voxd.utils.libw import verbo, verr


class AudioRecorder:
    """Stream microphone PCM to bounded temporary WAV chunks."""

    def __init__(
        self,
        *,
        samplerate: int = 16000,
        channels: int = 1,
        chunk_seconds: int = 300,
        input_device: str = "",
        prefer_pulse: bool = True,
    ):
        self.fs = int(samplerate)
        self.channels = int(channels)
        self.chunk_seconds = int(chunk_seconds)
        self.input_device = input_device
        self.prefer_pulse = prefer_pulse
        self.temp_dir = DATA_DIR / "temp"
        self.temp_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.temp_dir.chmod(0o700)
        self.is_recording = False
        self.last_temp_file: Path | None = None
        self.stream = None
        self._chunk_wave = None
        self._chunk_index = 0
        self._chunk_written_frames = 0
        self._chunk_target_frames = self.chunk_seconds * self.fs
        self._chunk_paths: list[Path] = []
        self._write_error: Exception | None = None

    def start_recording(self) -> None:
        verbo("[recorder] Recording started")
        self._discard_chunks()
        self._write_error = None
        self._open_new_chunk()

        preferred = self.input_device or ("pulse" if self.prefer_pulse else None)

        try:
            self._start_stream(preferred, self.fs)
            self.is_recording = True
            return
        except Exception as exc:
            verr(
                f"[recorder] Opening input at {self.fs} Hz failed ({exc}); "
                "trying the device default"
            )

        fallback_fs = self._default_sample_rate(preferred)
        self.fs = fallback_fs
        self._chunk_target_frames = self.chunk_seconds * self.fs
        self._discard_chunks()
        self._open_new_chunk()

        candidates = []
        if preferred != "pulse":
            candidates.append("pulse")
        candidates.append(None)
        last_error = None
        for device in candidates:
            try:
                self._start_stream(device, self.fs)
                self.is_recording = True
                return
            except Exception as exc:
                last_error = exc

        self.is_recording = False
        self._discard_chunks()
        raise RuntimeError(f"could not open an audio input stream: {last_error}")

    def _start_stream(self, device, sample_rate) -> None:
        stream = self._open_stream(device, sample_rate)
        try:
            stream.start()
        except Exception:
            try:
                stream.close()
            except Exception:
                pass
            raise
        self.stream = stream

    def _open_stream(self, device, sample_rate):
        kwargs = {
            "samplerate": sample_rate,
            "channels": self.channels,
            "callback": self._audio_callback,
        }
        if device:
            kwargs["device"] = device
        return sd.InputStream(**kwargs)

    def _default_sample_rate(self, device) -> int:
        try:
            info = sd.query_devices(device, "input") if device else sd.query_devices(kind="input")
            return int(info.get("default_samplerate") or 48000)
        except Exception:
            return 48000

    def _audio_callback(self, indata, frames, _time, status) -> None:
        if status:
            verbo(f"[recorder] Warning: {status}")
        if self._write_error is not None:
            return
        try:
            pcm = (np.clip(indata.copy(), -1.0, 1.0) * 32767.0).astype(np.int16)
            self._chunk_wave.writeframes(pcm.tobytes())
            self._chunk_written_frames += frames
            if self._chunk_written_frames >= self._chunk_target_frames:
                self._close_chunk()
                self._open_new_chunk()
        except Exception as exc:
            self._write_error = exc
            verr(f"[recorder] Chunk write failed: {exc}")

    def stop_recording(self, preserve: bool = False) -> Path | None:
        if not self.is_recording:
            return None

        verbo("[recorder] Stopping recording")
        stop_error = None
        if self.stream is not None:
            try:
                self.stream.stop()
            except Exception as exc:
                stop_error = exc
            try:
                self.stream.close()
            except Exception as exc:
                stop_error = stop_error or exc
            self.stream = None
        self.is_recording = False
        self._close_chunk()

        recording_error = self._write_error or stop_error
        if preserve or recording_error:
            output_path = RECORDINGS_DIR / self._timestamped_filename()
        else:
            output_path = self.temp_dir / "last_recording.wav"
        self._stitch_chunks(output_path)
        self.last_temp_file = output_path
        verbo(f"[recorder] Saved to {output_path}")
        if recording_error:
            raise RuntimeError(
                f"audio capture failed; partial recording preserved at {output_path}: "
                f"{recording_error}"
            )
        return output_path

    def _timestamped_filename(self) -> str:
        return f"{datetime.now():%Y%m%d_%H%M%S_%f}_recording.wav"

    def _open_new_chunk(self) -> None:
        self._chunk_index += 1
        self._chunk_written_frames = 0
        chunk_path = self.temp_dir / f"chunk_{self._chunk_index:04d}.wav"
        chunk_wave = wave.open(str(chunk_path), "wb")
        chunk_path.chmod(0o600)
        try:
            chunk_wave.setnchannels(self.channels)
            chunk_wave.setsampwidth(2)
            chunk_wave.setframerate(self.fs)
        except Exception:
            chunk_wave.close()
            try:
                chunk_path.unlink()
            except FileNotFoundError:
                pass
            raise
        self._chunk_paths.append(chunk_path)
        self._chunk_wave = chunk_wave

    def _close_chunk(self) -> None:
        if self._chunk_wave is not None:
            self._chunk_wave.close()
            self._chunk_wave = None

    def _discard_chunks(self) -> None:
        self._close_chunk()
        for path in self._chunk_paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self._chunk_paths = []
        self._chunk_index = 0
        self._chunk_written_frames = 0

    def _stitch_chunks(self, output_path: Path) -> None:
        if not self._chunk_paths:
            raise RuntimeError("no recorded audio chunks were produced")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with wave.open(str(output_path), "wb") as destination:
                destination.setnchannels(self.channels)
                destination.setsampwidth(2)
                destination.setframerate(self.fs)
                for path in self._chunk_paths:
                    with wave.open(str(path), "rb") as source:
                        destination.writeframes(source.readframes(source.getnframes()))
        except Exception:
            # Preserve chunks for manual recovery when stitching fails.
            raise
        else:
            output_path.chmod(0o600)
            self._discard_chunks()

    def cleanup_temp(self) -> None:
        if self.last_temp_file and self.last_temp_file.exists():
            self.last_temp_file.unlink()
