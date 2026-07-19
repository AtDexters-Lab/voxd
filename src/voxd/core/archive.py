from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import wave
from datetime import datetime
from pathlib import Path


class RecordingArchive:
    """Compress private recording bundles and enforce their storage quota."""

    def __init__(
        self,
        *,
        directory: Path | None = None,
        max_bytes: int = 5 * 1024 * 1024 * 1024,
        ffmpeg_path: str | None = None,
    ):
        if directory is None:
            from voxd.paths import RECORDINGS_DIR

            directory = RECORDINGS_DIR
        self.directory = Path(directory)
        self.max_bytes = max(0, int(max_bytes))
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")

    def store(self, wav_path: Path, metadata: dict) -> Path:
        source = Path(wav_path)
        if not source.is_file():
            raise FileNotFoundError(f"recording not found: {source}")

        self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.directory.chmod(0o700)
        audio_details = self._wav_details(source)
        final_audio = self.directory / f"{source.stem}.flac"
        encoding_error = None

        try:
            self._encode_flac(source, final_audio)
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            final_audio = self._retain_wav(source)
            encoding_error = str(exc)

        audio_details.update(
            {
                "codec": "flac" if final_audio.suffix == ".flac" else "pcm_s16le",
                "file": final_audio.name,
                "sha256": self._sha256(final_audio),
            }
        )
        if encoding_error:
            audio_details["compression_error"] = encoding_error

        document = {
            "schema_version": 1,
            "archived_at": datetime.now().astimezone().isoformat(),
            "audio": audio_details,
            **metadata,
        }
        sidecar = self.directory / f"{source.stem}.json"
        self._write_json(sidecar, document)
        self._prune()
        return final_audio

    def _encode_flac(self, source: Path, destination: Path) -> None:
        if not self.ffmpeg_path:
            raise RuntimeError("ffmpeg is unavailable")

        temporary = destination.with_suffix(".tmp.flac")
        try:
            subprocess.run(
                [
                    self.ffmpeg_path,
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-map_metadata",
                    "-1",
                    "-vn",
                    "-c:a",
                    "flac",
                    "-compression_level",
                    "8",
                    str(temporary),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=300,
            )
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise RuntimeError("ffmpeg produced no FLAC output")
            temporary.chmod(0o600)
            temporary.replace(destination)
            destination.chmod(0o600)
            source.unlink()
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _retain_wav(self, source: Path) -> Path:
        destination = self.directory / source.name
        if source != destination:
            source.replace(destination)
        destination.chmod(0o600)
        return destination

    @staticmethod
    def _wav_details(source: Path) -> dict:
        with wave.open(str(source), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            frames = wav_file.getnframes()
            return {
                "channels": wav_file.getnchannels(),
                "duration_seconds": round(frames / frame_rate, 3) if frame_rate else 0,
                "sample_rate_hz": frame_rate,
                "sample_width_bytes": wav_file.getsampwidth(),
            }

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_json(path: Path, document: dict) -> None:
        temporary = path.with_suffix(".tmp.json")
        try:
            temporary.write_text(
                json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.chmod(0o600)
            temporary.replace(path)
            path.chmod(0o600)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _prune(self) -> None:
        if self.max_bytes <= 0:
            return

        try:
            bundles: dict[str, list[Path]] = {}
            for path in self.directory.iterdir():
                if path.suffix not in {".flac", ".wav", ".json"}:
                    continue
                if not path.stem.endswith("_recording"):
                    continue
                bundles.setdefault(path.stem, []).append(path)

            ordered = sorted(
                bundles.values(),
                key=lambda files: min(path.stat().st_mtime for path in files),
            )
            total = sum(path.stat().st_size for files in ordered for path in files)
            while total > self.max_bytes and len(ordered) > 1:
                oldest = ordered.pop(0)
                for path in oldest:
                    try:
                        size = path.stat().st_size
                        path.unlink()
                        total -= size
                    except FileNotFoundError:
                        pass
        except OSError as exc:
            # The recording and its metadata are already durable. Quota
            # maintenance must not make a successful archive look failed.
            print(f"[archive] Could not enforce storage quota: {exc}", flush=True)
