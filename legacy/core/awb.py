"""AWB (AFS2) read + write paths.

Read path: thin wrapper over PyCriCodecsEx.awb.AWB — Quick Extract mode.
Write path: AWBBuilderFixed vendored with the KI-001 fix (over-pad when
header size was already aligned). Use this for Phase 4 inject rebuild
instead of PyCriCodecsEx.awb.AWBBuilder.
"""

from __future__ import annotations

import os
import threading
from io import BytesIO
from pathlib import Path
from struct import pack
from typing import Callable, Iterable

from PyCriCodecsEx.awb import AWB, AWBBuilder
from PyCriCodecsEx.chunk import AWBChunkHeader
from PyCriCodecsEx.hca import HCA, HCACodec

from .models import Waveform


ProgressCb = Callable[[int, int], None]  # (done, total)
LogCb = Callable[[str, str], None]        # (message, tag: "info"|"ok"|"error")


class AwbReader:
    """Open an AWB file, enumerate waveforms, extract them as WAV."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._awb = AWB(str(self.path))
        self._waveforms: list[Waveform] | None = None

    @property
    def numfiles(self) -> int:
        return self._awb.numfiles

    def waveforms(self) -> list[Waveform]:
        if self._waveforms is None:
            self._waveforms = list(self._iter_waveforms())
        return self._waveforms

    def _iter_waveforms(self) -> Iterable[Waveform]:
        for idx in range(self._awb.numfiles):
            blob = self._awb.get_file_at(idx)
            hca = HCA(blob)
            info = hca.hca
            yield Waveform.from_hca_header(
                index=idx,
                channels=int(info.get("ChannelCount", 0)),
                sample_rate=int(info.get("SampleRate", 0)),
                frame_count=int(info.get("FrameCount", 0)),
            )

    def extract_one(self, index: int, out_path: str | os.PathLike[str]) -> None:
        """Decode waveform `index` and write it as a WAV file."""
        blob = self._awb.get_file_at(index)
        codec = HCACodec(blob)
        codec.save(str(out_path))

    @property
    def subkey(self) -> int:
        return int(self._awb.subkey)

    @property
    def version(self) -> int:
        return int(self._awb.version)

    @property
    def align(self) -> int:
        return int(self._awb.align)

    @property
    def id_intsize(self) -> int:
        return int(self._awb.id_intsize)

    def extract_all(
        self,
        out_dir: str | os.PathLike[str],
        *,
        progress_cb: ProgressCb | None = None,
        log_cb: LogCb | None = None,
        stop_event: threading.Event | None = None,
    ) -> list[Path]:
        """Extract every waveform as `track_NNNN.wav` in `out_dir`.

        Returns the list of written paths. Honors `stop_event` for cancellation;
        a partial result is returned when cancelled.
        """
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)

        stem = self.path.stem
        written: list[Path] = []
        total = self._awb.numfiles

        for idx in range(total):
            if stop_event is not None and stop_event.is_set():
                break
            out_path = out / f"{stem}_track_{idx:04d}.wav"
            try:
                self.extract_one(idx, out_path)
                written.append(out_path)
                if log_cb:
                    log_cb(f"  extracted {out_path.name}", "ok")
            except Exception as e:  # noqa: BLE001 — surface decode errors to GUI
                if log_cb:
                    log_cb(f"  failed track {idx:04d}: {e}", "error")
            if progress_cb:
                progress_cb(idx + 1, total)

        return written


# ── KI-001: vendored AWBBuilder with corrected alignment math ─────────────────
#
# Upstream (PyCriCodecsEx 0.0.5) adds a full `align` block to `headersize`
# even when `headersize % align == 0`, which places all waveform offsets one
# alignment block past where the payloads were actually written. See
# docs/known_issues.md KI-001 for the minimal repro and root cause.
#
# This subclass overrides only `build()`. The constructor surface is inherited
# verbatim, so callers can swap `AWBBuilder` → `AWBBuilderFixed` with no other
# changes.

class AWBBuilderFixed(AWBBuilder):
    """Drop-in replacement for :class:`PyCriCodecsEx.awb.AWBBuilder` with
    KI-001 fixed. Use this for any writable-AWB path (Phase 4 inject).

    Rewritten to compute offsets by simulating the write sequence directly,
    instead of deriving from cumulative raw sizes. Upstream's cumulative
    approach silently desynchronizes from the write loop whenever a blob
    length isn't a multiple of `align` — which is the common case for HCA.
    """

    def build(self) -> bytes:
        numfiles = len(self.infiles)
        total_raw = sum(len(b) for b in self.infiles)

        if total_raw > 0xFFFFFFFF:
            offset_intsize = 8
            offset_strtype = "<Q"
        else:
            offset_intsize = 4
            offset_strtype = "<I"

        # Header layout: AWBChunkHeader (16) + id table + offset table.
        # The offset table has numfiles + 1 entries (the last is the EOF sentinel).
        header_raw_size = (
            16
            + self.id_intsize * numfiles
            + offset_intsize * (numfiles + 1)
        )

        # KI-001 FIX: header is padded to `align` only if it isn't already aligned.
        if header_raw_size % self.align == 0:
            header_padded_size = header_raw_size
        else:
            header_padded_size = (
                header_raw_size
                + (self.align - (header_raw_size % self.align))
            )

        # Simulate the payload-write sequence to produce the offset table.
        # ofs[i] = start of blob i. ofs[numfiles] = EOF (for size of last blob).
        ofs: list[int] = [header_padded_size]
        cursor = header_padded_size
        for idx, blob in enumerate(self.infiles):
            cursor += len(blob)
            if idx < numfiles - 1:
                # align up to where the NEXT blob will start
                rem = cursor % self.align
                if rem != 0:
                    cursor += self.align - rem
            ofs.append(cursor)

        # Build the header bytes.
        header = AWBChunkHeader.pack(
            b"AFS2", self.version, offset_intsize, self.id_intsize,
            numfiles, self.align, self.subkey,
        )
        id_strtype = f"<{self._stringtypes(self.id_intsize)}"
        for i in range(numfiles):
            header += pack(id_strtype, i)
        for v in ofs:
            header += pack(offset_strtype, v)
        # Pad the header out to `header_padded_size` (no-op when already aligned).
        if len(header) < header_padded_size:
            header = header.ljust(header_padded_size, b"\x00")

        # Write file.
        out = BytesIO()
        out.write(header)
        for idx, blob in enumerate(self.infiles):
            out.write(blob)
            if idx < numfiles - 1:
                pos = out.tell()
                rem = pos % self.align
                if rem != 0:
                    out.write(b"\x00" * (self.align - rem))
        return out.getvalue()


def rebuild_awb_bytes(
    blobs: list[bytes],
    *,
    source: AWB | None = None,
    subkey: int = 0,
    version: int = 2,
    id_intsize: int = 0x2,
    align: int = 0x20,
) -> bytes:
    """Build an AWB file using :class:`AWBBuilderFixed`.

    When `source` is given, format parameters (`subkey`, `version`, `id_intsize`,
    `align`) are inherited from it so a rebuild preserves the on-disk layout
    choices of the original bank. Explicit kwargs override the source.
    """
    if source is not None:
        subkey = source.subkey
        version = source.version
        id_intsize = source.id_intsize
        align = source.align
    return AWBBuilderFixed(
        blobs,
        subkey=subkey,
        version=version,
        id_intsize=id_intsize,
        align=align,
    ).build()
