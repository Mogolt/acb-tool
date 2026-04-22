"""Dataclasses shared by core and GUI.

Both Quick Mode (AWB-only) and Full Project Mode (ACB+AWB) produce the same
Waveform shape, so the GUI table renders identically regardless of entry path.
The Cue type is Full-Project-only (Quick mode has no cue graph).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Waveform:
    """A single HCA waveform entry.

    `index` is the AWB offset-table index used to retrieve the raw bytes —
    always populated. For waveforms sourced from the ACB, prefer metadata
    from ACB's WaveformTable (authoritative for NumSamples etc.) rather
    than re-deriving from the HCA header.
    """

    index: int
    channels: int
    sample_rate: int
    sample_count: int
    codec: str = "HCA"
    loop_flag: bool = False

    @property
    def duration_s(self) -> float:
        return self.sample_count / self.sample_rate if self.sample_rate else 0.0

    @classmethod
    def from_hca_header(cls, *, index: int, channels: int, sample_rate: int, frame_count: int) -> "Waveform":
        """Quick-Mode path: no ACB, derive sample_count from HCA frame count (1024 samples/frame)."""
        return cls(
            index=index,
            channels=channels,
            sample_rate=sample_rate,
            sample_count=frame_count * 1024,
        )

    @classmethod
    def from_acb_entry(cls, wf_payload: dict) -> "Waveform":
        """Project-Mode path: build from a PyCriCodecsEx WaveformTable `_payload` dict.

        Handles both simple schema (field `Id`) and extended schema
        (fields `StreamAwbId`/`MemoryAwbId`). See docs/phase2_acb_structure.md.
        """
        def v(key: str, default=None):
            val = wf_payload.get(key)
            return val[1] if val is not None else default

        streaming = v("Streaming", 0)
        if "StreamAwbId" in wf_payload and streaming == 1:
            awb_idx = v("StreamAwbId")
        elif "MemoryAwbId" in wf_payload:
            mem_id = v("MemoryAwbId")
            # Extended schema reserves 0xFFFF for "unused"
            awb_idx = v("StreamAwbId") if mem_id == 0xFFFF and "StreamAwbId" in wf_payload else mem_id
        elif "Id" in wf_payload:
            awb_idx = v("Id")
        else:
            raise ValueError(f"unknown WaveformTable schema, payload keys: {sorted(wf_payload)}")

        encode_type = v("EncodeType", 2)
        codec_name = {0: "ADX", 1: "PCM", 2: "HCA", 6: "HCAMX"}.get(encode_type, f"codec_{encode_type}")

        return cls(
            index=int(awb_idx),
            channels=int(v("NumChannels", 0)),
            sample_rate=int(v("SamplingRate", 0)),
            sample_count=int(v("NumSamples", 0)),
            codec=codec_name,
            loop_flag=bool(v("LoopFlag", 0)),
        )


@dataclass(frozen=True)
class Cue:
    """A named entry in the ACB cue table. Full Project Mode only."""

    cue_id: int
    name: str
    length_ms: int
    waveform_indices: tuple[int, ...]

    @property
    def length_s(self) -> float:
        return self.length_ms / 1000.0


@dataclass(frozen=True)
class Bank:
    """The ACB+AWB pair representing one sound bank in Full Project Mode."""

    name: str
    acb_path: str
    awb_path: str
    cues: tuple[Cue, ...]
    waveforms: tuple[Waveform, ...] = field(default_factory=tuple)
