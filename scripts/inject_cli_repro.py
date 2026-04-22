"""Phase 4 pre-work — minimal CLI inject repro.

Does the library-level inject pipeline actually work end-to-end? This script
proves it without any GUI:

  1. Synthesize a 440 Hz sine WAV as the replacement audio (distinctive —
     impossible to confuse with any RE4 sample).
  2. Load `test_files/switch/core.acb` + `core.awb`.
  3. Encode the synth WAV to HCA (HIGHEST quality — Phase 3 default).
  4. Rebuild the AWB with blob index 0 swapped for the new HCA.
  5. Patch the ACB's WaveformTable[0] mirror fields (NumChannels,
     SamplingRate, NumSamples).
  6. Serialize the modified ACB via UTFBuilder.
  7. Write modified core.acb + core.awb to test_files/switch_modified/.
  8. Re-open the modified pair with our own Project reader. Decode
     waveform 0. Compare against the synth source.

Pass criteria:
  - Reopened ACB reports channels=1, rate=44100, samples=44032.
  - PSNR(synth WAV, re-extracted WAV) >= 40 dB.
  - Original tone is audibly recoverable from the written .wav spot file.

Dev-only script. Run from the project root:
    .venv/Scripts/python.exe scripts/inject_cli_repro.py
"""

from __future__ import annotations

import io
import math
import struct
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.awb import AwbReader, rebuild_awb_bytes
from core.hca import Quality
from core.project import Project
from PyCriCodecsEx.awb import AWB
from PyCriCodecsEx.hca import HCA, HCACodec
from PyCriCodecsEx.utf import UTFBuilder


HERE = Path(__file__).resolve().parent.parent
SRC_DIR = HERE / "test_files" / "switch"
OUT_DIR = HERE / "test_files" / "switch_modified"


def synth_sine_wav_bytes(*, freq: float = 440.0, secs: float = 1.0, rate: int = 44100) -> bytes:
    """Generate a mono 16-bit PCM WAV as bytes."""
    n = int(rate * secs)
    samples = (int(30000 * math.sin(2 * math.pi * freq * i / rate)) for i in range(n))
    body = struct.pack(f"<{n}h", *samples)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(body)
    return buf.getvalue()


def wav_to_np(wav_bytes: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32768.0


def psnr_db(ref: np.ndarray, test: np.ndarray) -> float:
    n = min(len(ref), len(test))
    mse = float(np.mean((ref[:n] - test[:n]) ** 2))
    return math.inf if mse <= 0 else 20.0 * math.log10(1.0 / math.sqrt(mse))


def strip_trailing_zeros(b: bytes) -> bytes:
    return b.rstrip(b"\x00") or b


def _bio4evt_resample_and_cue_length_test() -> bool:
    """Regression for the Phase 4 hardware-test silent-audio issue.

    Replace a `bio4evt` waveform (source 48 kHz stereo) with a 44.1 kHz synth
    tone and verify:
      * the on-disk HCA is 48 kHz (auto-resampled)
      * the ACB mirror fields report 48 kHz
      * the CueTable.Length entries for cues referencing this waveform were
        updated to match the new waveform's duration (not left at the
        original cue's millisecond length).
    """
    import math
    import struct
    import wave

    from core.inject import InjectPlan, Replacement
    from core.project import Project

    print()
    print("-- bio4evt resample + cue-length regression test " + "-" * 22)

    bank_path = SRC_DIR / "bio4evt.acb"
    if not bank_path.is_file():
        print("  skip: test_files/switch/bio4evt.acb not present")
        return True

    # Synthesize a 0.6s 440 Hz MONO tone at 44.1 kHz.
    wav_path = OUT_DIR / "_bio4evt_synth_44k1.wav"
    rate_in = 44100
    n = int(rate_in * 0.6)
    samples = (int(30000 * math.sin(2 * math.pi * 440 * i / rate_in)) for i in range(n))
    body = struct.pack(f"<{n}h", *samples)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate_in)
        w.writeframes(body)
    wav_path.write_bytes(buf.getvalue())
    print(f"  synth: {wav_path.name} — 0.6 s  {rate_in} Hz mono")

    p = Project.open(bank_path)
    target_table_idx = 0  # any non-corner waveform
    src_wf = p.waveforms()[target_table_idx]
    cues_pointing_at = [c for c in p.cues() if target_table_idx in c.waveform_indices]
    if not cues_pointing_at:
        print(f"  skip: no cue references wf[{target_table_idx}] in bio4evt")
        return True
    orig_cue_length_ms = cues_pointing_at[0].length_ms
    print(f"  source  wf[{target_table_idx}]: "
          f"{src_wf.channels}ch {src_wf.sample_rate}Hz {src_wf.sample_count} samp")
    print(f"  source  cue[{cues_pointing_at[0].name!r}].Length = {orig_cue_length_ms} ms")

    plan = InjectPlan(p)
    plan.add(Replacement.from_wav(
        waveform_table_index=target_table_idx, wav_path=wav_path,
    ))
    result = plan.apply()
    mod_acb = OUT_DIR / "bio4evt.acb"
    mod_awb = OUT_DIR / "bio4evt.awb"
    mod_acb.write_bytes(result.modified_acb_bytes)
    mod_awb.write_bytes(result.modified_awb_bytes)

    p2 = Project.open(mod_acb)
    mod_wf = p2.waveforms()[target_table_idx]
    mod_cue = [c for c in p2.cues() if target_table_idx in c.waveform_indices][0]
    expected_ms = int(round(mod_wf.sample_count * 1000 / mod_wf.sample_rate))

    print(f"  modded  wf[{target_table_idx}]: "
          f"{mod_wf.channels}ch {mod_wf.sample_rate}Hz {mod_wf.sample_count} samp "
          f"({mod_wf.sample_count / mod_wf.sample_rate:.2f} s)")
    print(f"  modded  cue[{mod_cue.name!r}].Length = {mod_cue.length_ms} ms "
          f"(expected ~{expected_ms} ms)")

    ok_rate = mod_wf.sample_rate == src_wf.sample_rate  # must match source (48k)
    ok_cue_length = abs(mod_cue.length_ms - expected_ms) <= 2  # rounding tolerance
    ok_cue_length_changed = mod_cue.length_ms != orig_cue_length_ms
    print(f"    rate matches source (48k):  {ok_rate}")
    print(f"    cue length updated:         {ok_cue_length_changed} "
          f"(from {orig_cue_length_ms} -&gt; {mod_cue.length_ms})")
    print(f"    cue length ~ new duration:  {ok_cue_length}")

    ok = ok_rate and ok_cue_length_changed and ok_cue_length
    print(f"  -> {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # -- step 1: synth source ------------------------------------------------
    synth_wav = synth_sine_wav_bytes(freq=440.0, secs=1.0, rate=44100)
    print(f"[1] synth source WAV: {len(synth_wav):,} bytes, 1 s 440 Hz 44.1 kHz mono")

    # Also drop it to disk so it can be audibly compared against the round-trip
    (OUT_DIR / "_source_tone.wav").write_bytes(synth_wav)

    # -- step 2: load source ACB + AWB ---------------------------------------
    src_acb_path = SRC_DIR / "core.acb"
    src_awb_path = SRC_DIR / "core.awb"
    print(f"[2] loading {src_acb_path.name} + {src_awb_path.name}")
    from PyCriCodecsEx.acb import ACB

    src_acb = ACB(str(src_acb_path))
    src_awb = AWB(str(src_awb_path))

    # Sanity-print the "before" of waveform 0
    wf0 = src_acb.view.WaveformTable[0]
    before = dict(
        NumChannels=wf0._payload["NumChannels"][1],
        SamplingRate=wf0._payload["SamplingRate"][1],
        NumSamples=wf0._payload["NumSamples"][1],
    )
    print(f"    BEFORE  WaveformTable[0] = {before}")

    # -- step 3: encode synth WAV -&gt; HCA --------------------------------------
    new_hca_bytes = HCACodec(synth_wav, quality=Quality.HIGHEST.value).get_encoded()
    new_hca = HCA(new_hca_bytes)
    new_channels = int(new_hca.hca["ChannelCount"])
    new_rate     = int(new_hca.hca["SampleRate"])
    new_frames   = int(new_hca.hca["FrameCount"])
    new_samples  = new_frames * 1024
    print(f"[3] encoded HCA: {len(new_hca_bytes):,} bytes  "
          f"{new_channels}ch {new_rate}Hz {new_frames} frames = {new_samples} samples")

    # -- step 4: rebuild AWB with blob 0 replaced ----------------------------
    blobs: list[bytes] = []
    for i in range(src_awb.numfiles):
        if i == 0:
            blobs.append(new_hca_bytes)
        else:
            blobs.append(strip_trailing_zeros(src_awb.get_file_at(i)))
    new_awb_bytes = rebuild_awb_bytes(blobs, source=src_awb)
    print(f"[4] rebuilt AWB: {len(new_awb_bytes):,} bytes ({src_awb.numfiles} blobs, blob 0 replaced)")

    # -- step 5: patch ACB mirror fields -------------------------------------
    wf0.NumChannels = new_channels
    wf0.SamplingRate = new_rate
    wf0.NumSamples = new_samples
    # Don't touch: Id, Streaming, EncodeType, LoopFlag, ExtensionData.
    after = dict(
        NumChannels=wf0._payload["NumChannels"][1],
        SamplingRate=wf0._payload["SamplingRate"][1],
        NumSamples=wf0._payload["NumSamples"][1],
    )
    print(f"[5] AFTER   WaveformTable[0] = {after}")

    # -- step 6: serialize ACB -----------------------------------------------
    new_acb_bytes = UTFBuilder(
        src_acb.dictarray,
        encoding=src_acb.encoding,
        table_name=src_acb.table_name,
    ).bytes()
    print(f"[6] serialized modified ACB: {len(new_acb_bytes):,} bytes "
          f"(source was {src_acb_path.stat().st_size:,})")

    # -- step 7: write to disk -----------------------------------------------
    mod_acb_path = OUT_DIR / "core.acb"
    mod_awb_path = OUT_DIR / "core.awb"
    mod_acb_path.write_bytes(new_acb_bytes)
    mod_awb_path.write_bytes(new_awb_bytes)
    print(f"[7] wrote {mod_acb_path}")
    print(f"    wrote {mod_awb_path}")

    # -- step 8: verify — re-open modified pair, extract waveform 0 ---------
    print()
    print("-- verification -------------------------------------------------")
    mod_project = Project.open(mod_acb_path)
    wfs = mod_project.waveforms()
    mod_wf0 = wfs[0]
    print(f"  reopened waveform 0: "
          f"{mod_wf0.channels}ch {mod_wf0.sample_rate}Hz {mod_wf0.sample_count} samples")

    ok_channels = mod_wf0.channels == new_channels
    ok_rate     = mod_wf0.sample_rate == new_rate
    ok_samples  = mod_wf0.sample_count == new_samples
    print(f"    channels match: {ok_channels}   rate match: {ok_rate}   samples match: {ok_samples}")

    # Decode the replaced waveform
    blob = mod_project.awb._awb.get_file_at(mod_wf0.index)
    decoded_wav = HCACodec(strip_trailing_zeros(blob)).decode()
    (OUT_DIR / "_reextracted_tone.wav").write_bytes(decoded_wav)

    synth_np = wav_to_np(synth_wav)
    rt_np    = wav_to_np(decoded_wav)
    psnr = psnr_db(synth_np, rt_np)
    print(f"  PSNR(synth source vs round-tripped): {psnr:.2f} dB")

    # -- pass/fail gate -----------------------------------------------------
    print()
    passed = ok_channels and ok_rate and ok_samples and (psnr >= 40.0)
    if passed:
        print("  core round-trip: PASS - library-level inject pipeline is working.")
        print(f"  Listen: {OUT_DIR / '_source_tone.wav'} vs {OUT_DIR / '_reextracted_tone.wav'}")
    else:
        print("  core round-trip: FAIL")
        return 1

    # Phase 4.1 regression: resample + cue length patch on bio4evt
    if not _bio4evt_resample_and_cue_length_test():
        return 1
    # Phase 4.2 regression: loop preservation for looping cues
    if not _loop_preservation_test():
        return 1
    return 0


def _loop_preservation_test() -> bool:
    """Replacing a looping cue must produce an HCA with a `loop` chunk.

    Without it, the game plays the replacement once and then cuts to silence —
    the exact symptom hardware testing hit on BGM/long-ambient cues.
    """
    from PyCriCodecsEx.awb import AWB
    from core.inject import InjectPlan, Replacement
    from core.project import Project

    print()
    print("-- bio4evt loop preservation regression test " + "-" * 27)

    bank_path = SRC_DIR / "bio4evt.acb"
    if not bank_path.is_file():
        print("  skip: bio4evt not present")
        return True

    # Use the same plain 44.1 kHz synth WAV (no smpl chunk) as input.
    src_wav_path = OUT_DIR / "_bio4evt_synth_44k1.wav"
    if not src_wav_path.is_file():
        print("  skip: run the resample test first to produce the synth WAV")
        return True

    p = Project.open(bank_path)
    # Pick a waveform where LoopFlag=1 (expected for bio4evt across the board).
    target_idx = next(
        (i for i, w in enumerate(p.waveforms()) if w.loop_flag), None
    )
    if target_idx is None:
        print("  skip: no looping waveforms in bio4evt")
        return True
    src_wf = p.waveforms()[target_idx]
    print(f"  target wf[{target_idx}]: {src_wf.channels}ch {src_wf.sample_rate}Hz "
          f"loop_flag={src_wf.loop_flag}")

    plan = InjectPlan(p)
    plan.add(Replacement.from_wav(
        waveform_table_index=target_idx, wav_path=src_wav_path,
    ))
    result = plan.apply()
    mod_acb = OUT_DIR / "bio4evt.acb"
    mod_awb = OUT_DIR / "bio4evt.awb"
    mod_acb.write_bytes(result.modified_acb_bytes)
    mod_awb.write_bytes(result.modified_awb_bytes)

    # Pull the replaced blob and check for `loop` chunk in its header.
    awb = AWB(str(mod_awb))
    hca_blob = awb.get_file_at(p.waveforms()[target_idx].index)
    has_loop_magic = b"loop" in hca_blob[:200]
    print(f"  replaced HCA size: {len(hca_blob.rstrip(bytes([0]))):,} bytes")
    print(f"  loop chunk present in HCA header: {has_loop_magic}")

    # Also verify the ACB LoopFlag stayed intact (we never touched it but sanity-check).
    p2 = Project.open(mod_acb)
    mod_wf = p2.waveforms()[target_idx]
    print(f"  modded wf[{target_idx}]: loop_flag={mod_wf.loop_flag} "
          f"(source was {src_wf.loop_flag})")

    ok = has_loop_magic and mod_wf.loop_flag == src_wf.loop_flag
    print(f"  -> {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    sys.exit(main())
