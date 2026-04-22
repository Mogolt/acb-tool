# Phase 3 — HCA Encoder Validation (PSNR Baseline)

**Date:** 2026-04-22
**Gate:** `PSNR ≥ 40 dB on every sample in a 10-sample corpus` (see PLAN.md §4 Phase 3 row).
**Verdict:** ✅ **PASS** at `Quality.HIGHEST`. ❌ **FAIL** at `Quality.HIGH`.
**Decision:** default encoder quality is now `HIGHEST` for both the Convert tab and Phase 4 inject. Set in `core/hca.py::Quality.default` and in `encode_wav_to_hca(quality=...)` default.

---

## Method

Round-trip test (decode → re-encode → decode → compare):

1. Read raw HCA blob from Switch `.awb` via `AWB.get_file_at(i)`.
2. Decode to 16-bit WAV via `HCACodec(hca).decode()` — this is the **reference** (what the game plays, since CRI's offline encode already baked in quantization).
3. Re-encode that WAV via our encoder: `HCACodec(ref_wav_bytes, quality=<Q>).get_encoded()`.
4. Decode the re-encoded HCA back to WAV.
5. Compute `PSNR(reference, round_tripped)` on matched-length int16 → float64 normalized to `[-1, 1]`, peak=1.0, `PSNR = 20·log10(1/√MSE)`.

Harness: `scripts/validate_encoder.py`. Runs under the dev venv (uses numpy).

---

## Corpus (10 samples)

Mix of banks, sample rates, channel counts, durations, and content classes.

| # | Bank | AWB idx | Rate | Ch | Samples | Content class (best guess) |
|---|------|--------:|-----:|---:|--------:|----------------------------|
| 0 | `core`    |   0 | 44100 | 1 |   133 870 | Item-pickup SFX |
| 1 | `core`    |   2 | 44100 | 1 |    89 597 | UI |
| 2 | `core`    |  12 | 44100 | 1 |    11 481 | Short transient SFX (260 ms) |
| 3 | `core`    |  30 | 44100 | 1 |    11 463 | Mid-range SFX |
| 4 | `core`    |  64 | 44100 | 1 |    35 047 | Last entry |
| 5 | `bio4evt` |   0 | 48000 | 2 |    89 772 | Room ambience (short) |
| 6 | `bio4evt` |  94 | 48000 | 2 | 4 685 600 | Long ambience/music (~98 s) |
| 7 | `bio4evt` | 100 | 11025 | 1 |       431 | Extremely short (39 ms) |
| 8 | `bio4evt` | 153 | 48000 | 2 |   859 092 | Water ambience |
| 9 | `bio4evt` | 280 | 48000 | 2 |   697 776 | Event cue |

---

## Results

### At `Quality.HIGHEST` (shipped default) — PASS

| # | Label | PSNR (dB) |
|---|-------|----------:|
| 0 | core/ItemGet_18k (pickup SFX)                   |  75.76 |
| 1 | core/sub_in (UI)                                |  75.10 |
| 2 | core/hazusu_1 (short transient SFX)             |  49.13 |
| 3 | core/mid-range SFX                              |  55.32 |
| 4 | core/last entry                                 |  80.03 |
| 5 | bio4evt/track 0 (room ambience)                 |  76.00 |
| 6 | bio4evt/long cue (~98 s stereo)                 |  66.30 |
| 7 | bio4evt/11.025 kHz mono (39 ms)                 | 111.88 |
| 8 | bio4evt/r205_water-source (stereo water)        |  83.53 |
| 9 | bio4evt/track 280 (event)                       |  65.90 |

```
min  PSNR: 49.13 dB   (gate 40 dB, +9.13 dB margin)
mean PSNR: 73.90 dB
max  PSNR: 111.88 dB
gate (>= 40 dB on every sample): PASS
```

### At `Quality.HIGH` — FAIL (for historical comparison)

Same corpus, `quality=High`:

| # | Label | PSNR (dB) |
|---|-------|----------:|
| 0 | core/ItemGet_18k                                |  51.33 |
| 1 | core/sub_in                                     |  56.97 |
| **2** | **core/hazusu_1 (short SFX)**               | **35.32** ❌ |
| 3 | core/mid-range SFX                              |  41.11 |
| 4 | core/last entry                                 |  49.41 |
| 5 | bio4evt/track 0                                 |  58.18 |
| 6 | bio4evt/long cue                                |  56.11 |
| 7 | bio4evt/11.025 kHz mono                         | 109.66 |
| 8 | bio4evt/r205_water                              |  70.30 |
| 9 | bio4evt/track 280                               |  56.27 |

```
min  PSNR: 35.32 dB   ← below 40 dB gate
gate (>= 40 dB on every sample): FAIL
```

### Drilldown on sample 2 — quality sweep

| Quality | `hazusu_1` PSNR (dB) | `itemget_fixeq2` PSNR (dB) | `mid-range SFX` PSNR (dB) |
|---------|---------------------:|---------------------------:|--------------------------:|
| Highest |  49.13 |  59.04 |  55.32 |
| High    |  35.32 |  44.65 |  41.11 |
| Middle  |  33.61 |  42.44 |  38.94 |

Short sharp transients are where HCA quality matters most. `HIGH` is adequate for most content but fails on click-type SFX. `HIGHEST` clears the gate with margin on every category we tested.

---

## Implications for Phase 4 Inject

- **Use `Quality.HIGHEST` for replacement encodes.** Anything less risks audible quality loss on transient SFX, which is exactly the content class modders are most likely to swap (grunts, hits, pickups).
- File size trade-off vs `HIGH` is small (~1 %); not worth optimizing for.
- In-game listener validation in Phase 4 should pay particular attention to transient SFX to catch any residual artifacts that 49 dB PSNR wouldn't reveal.

---

## Sources

- Harness: `scripts/validate_encoder.py`
- Test corpus: `test_files/switch/core.awb`, `test_files/switch/bio4evt.awb`
- Encoder backend: PyCriCodecsEx 0.0.5, `CriCodecsEx.HcaEncode`
- PSNR reference: standard formula for normalized int16 audio (peak 1.0)
