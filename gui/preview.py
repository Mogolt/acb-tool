"""Non-blocking audio preview for all tabs.

Shared `AudioPreview` instance lives on the `App` and is passed to each tab,
so switching tabs (or clicking Preview on a different row) stops the current
clip automatically. Windows-only — uses stdlib `winsound`.

Playback strategy:
  * WAV on disk  → `winsound.PlaySound(path, SND_FILENAME | SND_ASYNC)`
  * WAV in bytes → write to a temp file, then play that as above.
    (`winsound` doesn't support `SND_MEMORY | SND_ASYNC` together — it raises
    ``RuntimeError: Cannot play asynchronously from memory``.)
  * HCA on disk / in bytes → decoded to WAV bytes via `HCACodec.decode()`,
    temp-filed, then played.

Decode happens in a background thread; the GUI never blocks.
"""

from __future__ import annotations

import os
import tempfile
import threading
import winsound
from pathlib import Path
from typing import Callable


class AudioPreview:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Temp file currently being played — deleted on next play / stop / close.
        self._temp_path: Path | None = None

    # ── WAV path (fast, no decode) ────────────────────────────────────────────

    def play_wav_file(self, path: str | os.PathLike[str]) -> None:
        """Play a WAV file on disk (WAV only; use play_path for HCA)."""
        self.stop()
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)

    def play_wav_bytes(self, wav_bytes: bytes) -> None:
        """Play WAV bytes held in memory via a temp file."""
        self.stop()
        fd, tmp = tempfile.mkstemp(prefix="acbtool_preview_", suffix=".wav")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(wav_bytes)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        with self._lock:
            self._temp_path = Path(tmp)
            winsound.PlaySound(str(self._temp_path), winsound.SND_FILENAME | winsound.SND_ASYNC)

    # ── HCA path (decode first, play async) ───────────────────────────────────

    def play_hca_bytes_async(
        self,
        hca_bytes: bytes,
        *,
        on_error: Callable[[str], None] | None = None,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        """Decode HCA in a worker thread, then play the resulting WAV.

        Optional `on_error(msg)` and `on_ready()` callbacks run on whatever
        thread fires them — the caller is responsible for marshaling back to
        the GUI thread if needed (typically via `widget.after(0, ...)`).
        """
        self.stop()

        def _work() -> None:
            try:
                # Import here so the test harness can stub PyCriCodecsEx if ever needed.
                from PyCriCodecsEx.hca import HCACodec
                # Strip any trailing AWB alignment padding before decoding.
                stripped = hca_bytes.rstrip(b"\x00") or hca_bytes
                wav_bytes = HCACodec(stripped).decode()
            except Exception as e:  # noqa: BLE001
                if on_error:
                    on_error(str(e))
                return
            self.play_wav_bytes(wav_bytes)
            if on_ready:
                on_ready()

        threading.Thread(target=_work, daemon=True).start()

    # ── dispatch helper ───────────────────────────────────────────────────────

    def play_path_async(
        self,
        path: str | os.PathLike[str],
        *,
        on_error: Callable[[str], None] | None = None,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        """Play any supported file path (`.wav` sync, `.hca` async-decoded)."""
        p = Path(path)
        ext = p.suffix.lower()
        if ext == ".wav":
            try:
                self.play_wav_file(p)
                if on_ready:
                    on_ready()
            except Exception as e:  # noqa: BLE001
                if on_error:
                    on_error(str(e))
            return
        if ext == ".hca":
            try:
                data = p.read_bytes()
            except Exception as e:  # noqa: BLE001
                if on_error:
                    on_error(str(e))
                return
            self.play_hca_bytes_async(data, on_error=on_error, on_ready=on_ready)
            return
        if on_error:
            on_error(f"unsupported preview extension: {ext}")

    # ── stop ──────────────────────────────────────────────────────────────────

    def stop(self) -> None:
        with self._lock:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except RuntimeError:
                pass
            if self._temp_path is not None:
                try:
                    self._temp_path.unlink()
                except OSError:
                    # Windows may briefly hold the file; ignore — the OS wipes
                    # %TEMP% on its own schedule.
                    pass
                self._temp_path = None
