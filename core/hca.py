"""HCA encode/decode wrappers + WAV resample helper.

Thin adapter over PyCriCodecsEx for the Convert tab (Phase 3) and Phase 4
inject path. RE4 is unencrypted so no key handling is exposed at this level.

The resample helper uses stdlib `audioop.ratecv` — linear interpolation,
acceptable quality for game modding where perfect resampling matters less
than engine-compatibility (matching the source bank's sample rate so Switch
RE4's preallocated playback buffers don't silently drop the audio).
"""

from __future__ import annotations

import audioop
import io
import os
import struct
import wave
from enum import Enum
from pathlib import Path

import CriCodecsEx
from PyCriCodecsEx.chunk import CriHcaQuality
from PyCriCodecsEx.hca import HCA, HCACodec


__all__ = [
    "HCA", "HCACodec", "Quality",
    "decode_hca_to_wav", "encode_wav_to_hca",
    "resample_wav_bytes", "ensure_wav_has_loop_smpl", "encode_wav_to_hca_bytes",
]


class Quality(Enum):
    """User-facing quality levels. Mapped 1:1 to PyCriCodecsEx's enum."""

    HIGHEST = CriHcaQuality.Highest
    HIGH    = CriHcaQuality.High
    MIDDLE  = CriHcaQuality.Middle
    LOW     = CriHcaQuality.Low
    LOWEST  = CriHcaQuality.Lowest

    @classmethod
    def default(cls) -> "Quality":
        # Phase 3 validation showed HIGH fails the 40 dB PSNR gate on short
        # transients (core/hazusu_1 at 35 dB). HIGHEST clears 40 dB across the
        # whole corpus. See docs/phase3_encoder_validation.md.
        return cls.HIGHEST


def decode_hca_to_wav(hca_path: str | os.PathLike[str], wav_path: str | os.PathLike[str]) -> None:
    """Decode an HCA file on disk to a WAV file on disk."""
    HCACodec(str(hca_path)).save(str(wav_path))


def resample_wav_bytes(wav_bytes: bytes, target_rate: int) -> bytes:
    """Return a WAV bytes blob resampled to ``target_rate``.

    No-op when the source is already at the target rate. 16-bit PCM is the
    only format HCA accepts anyway — we raise for anything else so the user
    sees a clear error instead of silent audio in-game.
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as r:
        channels = r.getnchannels()
        sampwidth = r.getsampwidth()
        rate = r.getframerate()
        frames = r.readframes(r.getnframes())

    if rate == target_rate:
        return wav_bytes

    if sampwidth != 2:
        raise ValueError(
            f"Resample requires 16-bit PCM WAV (got {sampwidth * 8}-bit). "
            f"Re-export your WAV as 16-bit and try again."
        )

    new_frames, _ = audioop.ratecv(frames, sampwidth, channels, rate, target_rate, None)

    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(target_rate)
        w.writeframes(new_frames)
    return out.getvalue()


def encode_wav_to_hca(
    wav_path: str | os.PathLike[str],
    hca_path: str | os.PathLike[str],
    *,
    quality: Quality = Quality.HIGHEST,
) -> None:
    """Encode a WAV file on disk to an HCA file on disk.

    PyCriCodecsEx's HCACodec auto-encodes on construction when given a WAV.
    """
    codec = HCACodec(str(wav_path), quality=quality.value)
    Path(hca_path).write_bytes(codec.get_encoded())


def ensure_wav_has_loop_smpl(wav_bytes: bytes) -> bytes:
    """Return a WAV with a ``smpl`` chunk carrying a full-file forward loop.

    If the input already has a ``smpl`` chunk, it is returned unchanged.
    Otherwise appends a ``smpl`` chunk describing a forward loop from sample
    0 to the last sample, with infinite play count. The CRI HCA encoder
    honors that and emits a ``loop`` chunk inside the HCA header, which the
    game engine then uses to seamlessly loop playback.

    Required for preserving loop behavior when replacing looping cues
    (e.g. music tracks in ``bio4bgm`` / long ambient loops in ``bio4evt``).
    """
    if wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
        raise ValueError("Not a RIFF WAVE file")

    # Walk chunks; bail early if a smpl already exists.
    pos = 12
    while pos + 8 <= len(wav_bytes):
        cid = wav_bytes[pos:pos + 4]
        csize = int.from_bytes(wav_bytes[pos + 4:pos + 8], "little")
        if cid == b"smpl":
            return wav_bytes
        pos += 8 + csize + (csize & 1)  # chunks are word-aligned

    with wave.open(io.BytesIO(wav_bytes), "rb") as r:
        total_samples = r.getnframes()
    if total_samples < 2:
        # Degenerate — nothing to loop.
        return wav_bytes

    # Build a standard smpl chunk with 1 forward loop spanning the whole file.
    smpl_header = struct.pack(
        "<IIIIIIIII",
        0,                     # Manufacturer
        0,                     # Product
        0,                     # Sample Period
        60,                    # MIDI Unity Note (middle C — arbitrary)
        0,                     # MIDI Pitch Fraction
        0,                     # SMPTE Format
        0,                     # SMPTE Offset
        1,                     # Num Sample Loops
        0,                     # Sampler Data size
    )
    loop_entry = struct.pack(
        "<IIIIII",
        0,                     # Cue Point ID
        0,                     # Type: 0 = forward loop
        0,                     # Start sample
        total_samples - 1,     # End sample (inclusive)
        0,                     # Fractional sample (none)
        0,                     # Play count: 0 = infinite
    )
    smpl_body = smpl_header + loop_entry
    smpl_chunk = b"smpl" + struct.pack("<I", len(smpl_body)) + smpl_body

    new_bytes = wav_bytes + smpl_chunk
    # Rewrite the outer RIFF chunk size.
    new_riff_size = len(new_bytes) - 8
    return new_bytes[:4] + struct.pack("<I", new_riff_size) + new_bytes[8:]


def encode_wav_to_hca_bytes(
    wav_bytes: bytes,
    *,
    quality: Quality = Quality.HIGHEST,
    preserve_looping: bool = False,
) -> bytes:
    """Encode WAV bytes to HCA bytes via the C++ encoder directly.

    We bypass :class:`HCACodec` because it hard-codes ``force_not_looping=True``
    (no loop chunk ever emitted) AND because PyCriCodecsEx 0.0.5's Python-side
    ``smpl`` parser has an off-by-four seek bug that crashes on any WAV with
    a smpl chunk. The C++ encoder doesn't have those issues.

    With ``preserve_looping=True`` and a ``smpl``-bearing WAV, the output HCA
    will contain a ``loop`` chunk the game engine uses for seamless loops.
    """
    force_not_looping = 0 if preserve_looping else 1
    return CriCodecsEx.HcaEncode(wav_bytes, force_not_looping, quality.value.value)
