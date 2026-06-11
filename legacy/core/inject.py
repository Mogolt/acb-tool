"""Phase 4 inject: targeted waveform replacement with ACB mirror-field patch.

A user queues up one or more single-waveform replacements via :class:`InjectPlan`,
then calls :meth:`InjectPlan.apply` to get back the modified ACB + AWB bytes
ready to be written to disk.

The CLI repro at ``scripts/inject_cli_repro.py`` validated this pipeline
end-to-end (75.59 dB PSNR on a 440 Hz tone replacement in ``core.acb``).
"""

from __future__ import annotations

import wave
from dataclasses import dataclass, field
from pathlib import Path

from PyCriCodecsEx.hca import HCA, HCACodec
from PyCriCodecsEx.utf import UTFBuilder

from .awb import rebuild_awb_bytes
from .hca import (
    Quality,
    encode_wav_to_hca_bytes,
    ensure_wav_has_loop_smpl,
    resample_wav_bytes,
)
from .project import Project


def _strip_trailing_zeros(b: bytes) -> bytes:
    return b.rstrip(b"\x00") or b


@dataclass(frozen=True)
class Replacement:
    """One queued waveform swap.

    ``waveform_table_index`` points into ``Project.waveforms()``. The AWB index
    is resolved from that entry at apply time.
    """

    waveform_table_index: int
    replacement_wav_path: str
    quality: Quality = Quality.HIGHEST

    # Derived metadata surfaced to the GUI "pending replacements" panel.
    new_channels: int = 0
    new_sample_rate: int = 0
    new_sample_count: int = 0
    new_hca_size: int = 0

    @classmethod
    def from_wav(
        cls,
        *,
        waveform_table_index: int,
        wav_path: str | Path,
        quality: Quality = Quality.HIGHEST,
    ) -> "Replacement":
        """Read WAV metadata only. Encoding is deferred to :meth:`InjectPlan.apply`
        where we also have the source sample rate and can auto-resample.

        Queueing is therefore instant; the (potentially slow) HCA encode only
        runs once per replacement, when the user actually hits Save.
        """
        with wave.open(str(wav_path), "rb") as r:
            channels = r.getnchannels()
            rate = r.getframerate()
            n_samples = r.getnframes()
        return cls(
            waveform_table_index=waveform_table_index,
            replacement_wav_path=str(wav_path),
            quality=quality,
            new_channels=channels,
            new_sample_rate=rate,
            new_sample_count=n_samples,
            new_hca_size=0,  # not known until encode
        )


@dataclass
class ApplyResult:
    modified_acb_bytes: bytes
    modified_awb_bytes: bytes
    replacements_applied: int


class InjectPlan:
    """Collects replacements and applies them in one atomic rebuild.

    Workflow (GUI):
        plan = InjectPlan(project)
        plan.add(Replacement.from_wav(waveform_table_index=0, wav_path=...))
        plan.add(Replacement.from_wav(waveform_table_index=12, wav_path=...))
        result = plan.apply()
        Path(out_acb).write_bytes(result.modified_acb_bytes)
        Path(out_awb).write_bytes(result.modified_awb_bytes)
    """

    def __init__(self, project: Project) -> None:
        self.project = project
        self._replacements: dict[int, Replacement] = {}

    # ── queue management ─────────────────────────────────────────────────────

    def add(self, r: Replacement) -> None:
        """Queue a replacement. If the same waveform is already queued, overwrite."""
        self._validate(r)
        self._replacements[r.waveform_table_index] = r

    def remove(self, waveform_table_index: int) -> None:
        self._replacements.pop(waveform_table_index, None)

    def clear(self) -> None:
        self._replacements.clear()

    def pending(self) -> list[Replacement]:
        return [self._replacements[k] for k in sorted(self._replacements)]

    def _validate(self, r: Replacement) -> None:
        wfs = self.project.waveforms()
        if r.waveform_table_index < 0 or r.waveform_table_index >= len(wfs):
            raise ValueError(
                f"waveform_table_index {r.waveform_table_index} out of range "
                f"(bank has {len(wfs)} waveforms)"
            )
        if not Path(r.replacement_wav_path).is_file():
            raise FileNotFoundError(r.replacement_wav_path)

    # ── apply ────────────────────────────────────────────────────────────────

    def apply(self) -> ApplyResult:
        """Produce modified ACB + AWB bytes. Does not write to disk.

        For each queued replacement:
          * Auto-resample the WAV to match the source waveform's sample rate
            before encoding (Switch RE4 silently drops audio when the bank's
            on-disk rate doesn't match what the engine preallocated for).
          * Encode at the replacement's requested quality (HIGHEST default).
          * Patch WaveformTable mirror fields (NumChannels, SamplingRate,
            NumSamples).
          * Patch CueTable.Length for every cue that references the replaced
            waveform so cues don't get truncated mid-playback.
        """
        if not self._replacements:
            raise ValueError("no replacements queued")

        src_acb = self.project.acb._acb            # raw PyCriCodecsEx ACB
        src_awb = self.project.awb._awb            # raw PyCriCodecsEx AWB
        waveforms = self.project.waveforms()
        cues = self.project.cues()

        replacement_blobs: dict[int, bytes] = {}   # awb_index -> new HCA bytes
        replacement_meta:  dict[int, dict] = {}    # waveform_table_index -> ACB mirror fields

        for r in self.pending():
            wf = waveforms[r.waveform_table_index]
            target_rate = wf.sample_rate

            # Read the WAV, resample if the source bank expects a different rate.
            wav_bytes = Path(r.replacement_wav_path).read_bytes()
            if target_rate and target_rate != r.new_sample_rate:
                wav_bytes = resample_wav_bytes(wav_bytes, target_rate)

            # If the original waveform loops, inject a full-file forward loop
            # into the WAV so the C++ encoder emits a `loop` chunk in the HCA.
            # Without this, replacing BGM/long ambient cues plays the audio
            # once then goes silent — exactly what hardware testing hit.
            preserve_looping = bool(wf.loop_flag)
            if preserve_looping:
                wav_bytes = ensure_wav_has_loop_smpl(wav_bytes)

            # Encode (direct C++ path — bypasses HCACodec's hard-coded
            # force_not_looping=True and the broken smpl Python parser).
            hca_bytes = encode_wav_to_hca_bytes(
                wav_bytes, quality=r.quality, preserve_looping=preserve_looping,
            )
            h = HCA(hca_bytes)

            replacement_blobs[wf.index] = hca_bytes
            replacement_meta[r.waveform_table_index] = dict(
                NumChannels=int(h.hca["ChannelCount"]),
                SamplingRate=int(h.hca["SampleRate"]),
                NumSamples=int(h.hca["FrameCount"]) * 1024,
                Looping=preserve_looping,
            )

        # Rebuild AWB: use replacements where we have them, otherwise pass the
        # original blob through (with its trailing alignment pad stripped).
        new_blobs: list[bytes] = []
        for i in range(src_awb.numfiles):
            if i in replacement_blobs:
                new_blobs.append(replacement_blobs[i])
            else:
                new_blobs.append(_strip_trailing_zeros(src_awb.get_file_at(i)))
        new_awb_bytes = rebuild_awb_bytes(new_blobs, source=src_awb)

        # Patch ACB WaveformTable mirror fields.
        for table_idx, meta in replacement_meta.items():
            wf_entry = src_acb.view.WaveformTable[table_idx]
            wf_entry.NumChannels = meta["NumChannels"]
            wf_entry.SamplingRate = meta["SamplingRate"]
            wf_entry.NumSamples = meta["NumSamples"]
            # Don't touch Id / StreamAwbId / MemoryAwbId / EncodeType / Streaming
            # / LoopFlag / ExtensionData — identity preserved across inject.

        # Patch CueTable.Length for every cue that references a replaced waveform.
        # Without this, cues get truncated at their original length even if the
        # replacement is longer — which is the silent-audio gotcha we hit on
        # first hardware test of `bio4evt`.
        for cue_idx, cue in enumerate(cues):
            for table_idx, meta in replacement_meta.items():
                if table_idx in cue.waveform_indices:
                    new_len_ms = int(round(
                        meta["NumSamples"] * 1000 / meta["SamplingRate"]
                    ))
                    src_acb.view.CueTable[cue_idx].Length = new_len_ms
                    break  # one replacement is enough to resize the cue

        # Serialize modified ACB.
        new_acb_bytes = UTFBuilder(
            src_acb.dictarray,
            encoding=src_acb.encoding,
            table_name=src_acb.table_name,
        ).bytes()

        return ApplyResult(
            modified_acb_bytes=new_acb_bytes,
            modified_awb_bytes=new_awb_bytes,
            replacements_applied=len(self._replacements),
        )
