"""ACB read path for Full Project Mode.

Resolves cues to waveform indices across both schema variants seen in RE4
Switch banks (simple `Id`, extended `StreamAwbId`/`MemoryAwbId`) and both
reference types seen (`0x01` direct, `0x03` sequence). See
`docs/phase2_acb_structure.md` for schema details.
"""

from __future__ import annotations

import os
from pathlib import Path

from PyCriCodecsEx.acb import ACB

from .models import Cue, Waveform


class AcbReader:
    """Read-only view over an ACB file."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._acb = ACB(str(self.path))
        self._view = self._acb.view

        self._name_by_cue_idx: dict[int, str] = {
            int(cn._payload["CueIndex"][1]): str(cn._payload["CueName"][1])
            for cn in self._view.CueNameTable
        }

        self._waveforms: tuple[Waveform, ...] | None = None
        self._cues: tuple[Cue, ...] | None = None

    # ── basic metadata ────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return str(self._view.Name)

    @property
    def version_string(self) -> str:
        try:
            return str(self._view.VersionString).strip()
        except Exception:  # noqa: BLE001
            return ""

    # ── waveform table ────────────────────────────────────────────────────────

    def waveforms(self) -> tuple[Waveform, ...]:
        if self._waveforms is None:
            self._waveforms = tuple(
                Waveform.from_acb_entry(wf._payload) for wf in self._view.WaveformTable
            )
        return self._waveforms

    # ── cue resolution ────────────────────────────────────────────────────────

    def cues(self) -> tuple[Cue, ...]:
        if self._cues is None:
            self._cues = tuple(self._build_cues())
        return self._cues

    def _build_cues(self) -> list[Cue]:
        out: list[Cue] = []
        for cue_idx, ct in enumerate(self._view.CueTable):
            cue_id = int(ct._payload["CueId"][1])
            name = self._name_by_cue_idx.get(
                cue_idx,
                self._name_by_cue_idx.get(cue_id, f"cue_{cue_id:05d}"),
            )
            ref_type = int(ct._payload["ReferenceType"][1])
            ref_idx = int(ct._payload["ReferenceIndex"][1])
            length_ms = int(ct._payload["Length"][1])

            wf_indices = tuple(self._resolve_reference(ref_type, ref_idx))
            out.append(Cue(
                cue_id=cue_id,
                name=name,
                length_ms=length_ms,
                waveform_indices=wf_indices,
            ))
        return out

    def _resolve_reference(self, ref_type: int, ref_idx: int) -> list[int]:
        """Return a list of WaveformTable indices reached from a cue.

        Only types 0x01 (direct) and 0x03 (sequence with direct track->waveform
        indices) are seen in RE4 Switch banks. Unknown types return [] so the
        GUI can still render the cue name with a 'no-waveform' indicator.
        """
        if ref_type == 0x01:
            return [ref_idx]
        if ref_type == 0x03:
            try:
                seq = self._view.SequenceTable[ref_idx]
            except (IndexError, AssertionError):
                return []
            num_tracks = int(seq._payload["NumTracks"][1])
            track_index_blob = seq._payload["TrackIndex"][1]
            return [
                int.from_bytes(track_index_blob[i * 2 : i * 2 + 2], "big")
                for i in range(num_tracks)
            ]
        # 0x02 Synth / 0x08 BlockSequence — not seen in RE4; surface as no-op.
        return []

    # ── utility ───────────────────────────────────────────────────────────────

    def paired_awb_path(self) -> Path:
        """Return the expected companion AWB path (same stem, `.awb` extension)."""
        return self.path.with_suffix(".awb")
