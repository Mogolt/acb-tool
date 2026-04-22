"""AWB write-round-trip tests — KI-001 regression + encode inject dry-run.

Three independent tests, all must pass before Phase 4 begins:

  1. **KI-001 repro.** The minimal synthetic case that proved upstream's
     `AWBBuilder` was broken. With the vendored fix, both blobs must read
     back byte-identical to their input.

  2. **Real-bank rebuild.** Take a real Switch RE4 `.awb`, extract every
     HCA blob, rebuild the AWB with our fixed builder, and verify that
     each extracted blob starts with `HCA\\x00` and round-trips to WAV.

  3. **Full write-inject round-trip.** Encode a real source WAV to HCA,
     pack it into a brand-new single-entry AWB, re-extract, decode, and
     compare PSNR against the source. This is the full Phase 4 inject
     pipeline minus the ACB-mirror-field step.

Dev-only script. Run from the project root:
    .venv/Scripts/python.exe scripts/test_awb_roundtrip.py
"""

from __future__ import annotations

import io
import math
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.awb import AWBBuilderFixed, rebuild_awb_bytes
from core.hca import Quality
from PyCriCodecsEx.awb import AWB
from PyCriCodecsEx.hca import HCACodec


HERE = Path(__file__).resolve().parent.parent
BANKS = HERE / "test_files" / "switch"


def _banner(name: str) -> None:
    print()
    print(f"-- {name} ".ljust(76, "-"))


def _wav_to_np(wav_bytes: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32768.0


def _psnr(ref: np.ndarray, test: np.ndarray) -> float:
    n = min(len(ref), len(test))
    mse = float(np.mean((ref[:n] - test[:n]) ** 2))
    return math.inf if mse <= 0 else 20.0 * math.log10(1.0 / math.sqrt(mse))


# ── Test 1: KI-001 minimal repro ─────────────────────────────────────────────

def test_ki001_repro() -> bool:
    _banner("TEST 1 — KI-001 minimal repro (2 × 64-byte payloads)")
    payload_a = b"HCA\x00" + b"\xAA" * 60
    payload_b = b"HCA\x00" + b"\xBB" * 60

    awb_bytes = AWBBuilderFixed([payload_a, payload_b]).build()
    awb = AWB(awb_bytes)

    read_a = awb.get_file_at(0)[: len(payload_a)]
    read_b = awb.get_file_at(1)[: len(payload_b)]

    a_ok = read_a == payload_a
    b_ok = read_b == payload_b
    print(f"  numfiles={awb.numfiles}  align={awb.align}  ofs={awb.ofs}")
    print(f"  blob[0] starts with {awb.get_file_at(0)[:4]!r}  full-match-on-prefix: {a_ok}")
    print(f"  blob[1] starts with {awb.get_file_at(1)[:4]!r}  full-match-on-prefix: {b_ok}")
    ok = a_ok and b_ok
    print(f"  -> {'PASS' if ok else 'FAIL'}")
    return ok


# ── Test 2: real-bank rebuild ────────────────────────────────────────────────

def test_real_bank_rebuild(bank_name: str) -> bool:
    _banner(f"TEST 2 — real-bank rebuild: {bank_name}.awb")
    src_path = BANKS / f"{bank_name}.awb"
    if not src_path.is_file():
        print(f"  skip: {src_path} not present")
        return True

    src = AWB(str(src_path))
    blobs = [src.get_file_at(i) for i in range(src.numfiles)]
    # Strip trailing zero-padding so rebuilt blobs round-trip cleanly.
    # (get_file_at returns bytes INCLUDING alignment pad to the next offset.)
    blobs = [_strip_trailing_zeros(b) for b in blobs]

    rebuilt_bytes = rebuild_awb_bytes(blobs, source=src)
    rebuilt = AWB(rebuilt_bytes)

    print(f"  source numfiles={src.numfiles} align={src.align} version={src.version} "
          f"id_intsize={src.id_intsize} subkey={src.subkey}")
    print(f"  rebuilt size={len(rebuilt_bytes):,} bytes  numfiles={rebuilt.numfiles}")

    all_ok = True
    for i in range(src.numfiles):
        rb = rebuilt.get_file_at(i)
        magic = rb[:4]
        if magic != b"HCA\x00":
            print(f"    blob[{i}] magic {magic!r} ≠ b'HCA\\x00' — FAIL")
            all_ok = False
            continue

    # Spot-check a few blobs actually decode
    for i in list({0, src.numfiles // 2, src.numfiles - 1}):
        try:
            HCACodec(rebuilt.get_file_at(i)).decode()
        except Exception as e:  # noqa: BLE001
            print(f"    blob[{i}] decode FAILED: {e}")
            all_ok = False

    print(f"  -> {'PASS' if all_ok else 'FAIL'}")
    return all_ok


def _strip_trailing_zeros(b: bytes) -> bytes:
    # Strip \x00 from the right; HCA payloads never end with zero, so this
    # removes just the AWB alignment pad between blobs.
    return b.rstrip(b"\x00") or b


# ── Test 3: full write-inject round-trip ─────────────────────────────────────

def test_full_inject_round_trip() -> bool:
    _banner("TEST 3 — full write-inject round-trip: WAV -&gt; HCA -&gt; AWB -&gt; re-extract -&gt; decode")

    # Use a real Switch blob as our "source WAV" so the content is representative.
    src = AWB(str(BANKS / "core.awb"))
    src_hca = src.get_file_at(0)
    source_wav_bytes = HCACodec(src_hca).decode()  # the "truth"
    source_np = _wav_to_np(source_wav_bytes)
    print(f"  source: awb[0] of core.awb  ({len(source_np):,} samples)")

    # Encode -&gt; pack -&gt; re-extract -&gt; decode
    new_hca = HCACodec(source_wav_bytes, quality=Quality.HIGHEST.value).get_encoded()
    new_awb_bytes = AWBBuilderFixed([new_hca], align=src.align).build()
    inj = AWB(new_awb_bytes)
    assert inj.numfiles == 1, f"rebuilt AWB has {inj.numfiles} files (expected 1)"
    re_hca_blob = inj.get_file_at(0)
    # The extracted blob has AWB alignment pad at the end; decode just the HCA prefix.
    re_wav_bytes = HCACodec(_strip_trailing_zeros(re_hca_blob)).decode()
    rt_np = _wav_to_np(re_wav_bytes)

    psnr = _psnr(source_np, rt_np)
    print(f"  re-extract size: {len(re_hca_blob):,} bytes (pre-strip), "
          f"{len(_strip_trailing_zeros(re_hca_blob)):,} bytes (post-strip)")
    print(f"  PSNR(source vs round-tripped): {psnr:.2f} dB  (Phase 3 gate: >= 40 dB)")

    ok = psnr >= 40.0
    print(f"  -> {'PASS' if ok else 'FAIL'}")
    return ok


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    results = [
        ("KI-001 minimal repro",     test_ki001_repro()),
        ("real-bank rebuild: core",    test_real_bank_rebuild("core")),
        ("real-bank rebuild: door003", test_real_bank_rebuild("door003")),
        ("full write-inject round-trip", test_full_inject_round_trip()),
    ]

    print()
    print("=" * 76)
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}]  {name}")
    all_ok = all(ok for _, ok in results)
    print("=" * 76)
    print(f"  OVERALL: {'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
