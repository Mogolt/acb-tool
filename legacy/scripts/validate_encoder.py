"""Phase 3 encoder validation harness — PSNR round-trip.

For each selected waveform:
  1. Read HCA blob from AWB (reference encode, done by CRI offline).
  2. Decode to WAV via PyCriCodecsEx. This is the listener's ground-truth "what
     the game plays."
  3. Re-encode that WAV to HCA with our encoder.
  4. Decode the re-encoded HCA back to WAV.
  5. Compute PSNR(ref_wav, re_encoded_wav).

Passing PSNR bar: >= 40 dB (Phase 3 gate, see docs/PLAN.md).

Uses numpy for PSNR math (dev-only dependency; not shipped in the installer).

Run from the project root:
    .venv/Scripts/python.exe scripts/validate_encoder.py
"""

from __future__ import annotations

import io
import math
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.hca import Quality
from PyCriCodecsEx.awb import AWB
from PyCriCodecsEx.hca import HCACodec


@dataclass(frozen=True)
class Sample:
    bank: str
    awb_idx: int
    label: str  # human-friendly label (e.g. the cue name or "core/short SFX")


# Ten hand-picked samples: mix of short SFX, medium, long, from two banks + two
# sample rates. Chosen to cover the duration/content range RE4 actually uses.
SAMPLES: list[Sample] = [
    Sample("core",    0,   "core/ItemGet_18k (3.04s 44.1kHz mono — pickup SFX)"),
    Sample("core",    2,   "core/sub_in (2.03s 44.1kHz mono — UI)"),
    Sample("core",    12,  "core/hazusu_1 (short SFX)"),
    Sample("core",    30,  "core/mid-range SFX"),
    Sample("core",    64,  "core/last entry"),
    Sample("bio4evt", 0,   "bio4evt/track 0 (48kHz stereo — room ambience)"),
    Sample("bio4evt", 94,  "bio4evt/long cue (stereo music/ambience)"),
    Sample("bio4evt", 100, "bio4evt/mid cue"),
    Sample("bio4evt", 153, "bio4evt/r205_water-source (stereo water ambience)"),
    Sample("bio4evt", 280, "bio4evt/track 280 (last, likely short SFX)"),
]


def wav_bytes_to_np(wav_bytes: bytes) -> tuple[np.ndarray, int, int]:
    """Return (samples as float64 in [-1, 1], sample_rate, channels)."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        assert w.getsampwidth() == 2, f"expected 16-bit, got {w.getsampwidth()*8}-bit"
        n_frames = w.getnframes()
        frames = w.readframes(n_frames)
        rate = w.getframerate()
        channels = w.getnchannels()
    arr = np.frombuffer(frames, dtype="<i2").astype(np.float64)
    # normalize to [-1, 1]
    arr /= 32768.0
    return arr, rate, channels


def psnr_db(reference: np.ndarray, test: np.ndarray) -> float:
    n = min(len(reference), len(test))
    ref = reference[:n]
    tst = test[:n]
    mse = float(np.mean((ref - tst) ** 2))
    if mse <= 0.0:
        return math.inf
    # Peak amplitude for normalized int16 is 1.0
    return 20.0 * math.log10(1.0 / math.sqrt(mse))


def run_sample(awb: AWB, s: Sample) -> dict:
    hca_orig = awb.get_file_at(s.awb_idx)

    # Stage 2: reference WAV (CRI's encode → PyCriCodecsEx decode)
    ref_wav_bytes = HCACodec(hca_orig).decode()
    ref, rate, channels = wav_bytes_to_np(ref_wav_bytes)

    # Stage 3: re-encode our decoded WAV. Pass bytes directly to avoid the
    # double-FileIO path handling in HCACodec (WinError 267 on Windows).
    re_codec = HCACodec(ref_wav_bytes, quality=Quality.HIGHEST.value)
    reencoded_hca = re_codec.get_encoded()

    # Stage 4: decode re-encoded HCA
    rt_wav_bytes = HCACodec(reencoded_hca).decode()
    rt, _, _ = wav_bytes_to_np(rt_wav_bytes)

    # Stage 5: PSNR
    psnr = psnr_db(ref, rt)

    return {
        "label":       s.label,
        "bank":        s.bank,
        "awb_idx":     s.awb_idx,
        "sample_rate": rate,
        "channels":    channels,
        "ref_samples": len(ref),
        "rt_samples":  len(rt),
        "psnr_db":     psnr,
    }


def main() -> int:
    here = Path(__file__).resolve().parent.parent
    awbs: dict[str, AWB] = {}
    for bank in {s.bank for s in SAMPLES}:
        awb_path = here / "test_files" / "switch" / f"{bank}.awb"
        if not awb_path.is_file():
            print(f"error: missing test file {awb_path}", file=sys.stderr)
            return 2
        awbs[bank] = AWB(str(awb_path))

    print(f"{'#':>2} {'label':<58} {'rate':>6} {'ch':>2} {'samples':>9} {'PSNR (dB)':>12}")
    print("-" * 94)
    results = []
    for i, s in enumerate(SAMPLES):
        try:
            r = run_sample(awbs[s.bank], s)
        except Exception as e:  # noqa: BLE001
            print(f"{i:>2} {s.label:<58}  ERROR: {e}")
            results.append({"label": s.label, "error": str(e)})
            continue
        results.append(r)
        print(f"{i:>2} {r['label']:<58} {r['sample_rate']:>6} {r['channels']:>2} "
              f"{r['ref_samples']:>9} {r['psnr_db']:>12.2f}")

    psnrs = [r["psnr_db"] for r in results if "psnr_db" in r and math.isfinite(r["psnr_db"])]
    print("-" * 94)
    if psnrs:
        print(f"{'min PSNR':>70}: {min(psnrs):>7.2f} dB")
        print(f"{'mean PSNR':>70}: {sum(psnrs)/len(psnrs):>7.2f} dB")
        print(f"{'max PSNR':>70}: {max(psnrs):>7.2f} dB")
        gate = 40.0
        passed = all(p >= gate for p in psnrs)
        print(f"{'gate (>= 40 dB on every sample)':>70}: {'PASS' if passed else 'FAIL'}")
        return 0 if passed else 1
    print("no PSNR results produced")
    return 2


if __name__ == "__main__":
    sys.exit(main())
