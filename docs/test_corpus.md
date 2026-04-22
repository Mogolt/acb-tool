# Test Corpus

Template. Zulo: fill in as dumps are gathered / phases land. Keep one row per file, one section per phase.

---

## Source dumps

| Platform | Dump location | Date acquired | Notes |
|----------|--------------|---------------|-------|
| Switch | *(fill in)* | *(fill in)* | Full cartridge dump; `sound/` confirmed ACB/AWB, no CPK, unencrypted. |
| PS4 | *(pending)* | — | Phase 0 spot-check pending. |

---

## Per-phase test files

### Phase 1 — spike / round-trip

| File | Platform | Purpose | Expected behavior |
|------|----------|---------|-------------------|
| `core.acb` + `core.awb` | Switch | Smallest typical bank. Round-trip extract → re-inject same bytes → compare byte-for-byte. | Byte-identical round-trip, OR a list of drifted fields + proof the engine ignores them. |
| *(any small bank)* | PS4 | Parity check once PS4 dump lands. | Same as above. |

**Golden extractions:** after Phase 1 extract succeeds, hash every output WAV (SHA-256) and record here. Any future Phase 2+ regression that changes these hashes is a bug.

- `core/track_000.wav` — `(fill in after Phase 1)`
- `core/track_001.wav` — `(fill in after Phase 1)`

### Phase 2 — Browse + Extract (both modes, both platforms)

| File | Platform | Mode | Expected |
|------|----------|------|----------|
| `core.acb`+`.awb` | Switch | Full Project | Cue tree visible with human-readable names *(assuming Phase 1 confirms names present)*. Named WAV extraction. |
| `bio4evt.acb`+`.awb` | Switch | Full Project | Larger cue tree; all event SFX extract named. |
| `core.awb` alone | Switch | Quick Extract | Numbered `track_NNN.wav` extraction; no cue names. |
| `door003.acb`+`.awb` | Switch | Full Project | Small per-door bank — quick regression target. |
| *(equivalents)* | PS4 | both | Parity with Switch results. |

### Phase 3 — Convert (WAV ↔ HCA)

| Test | Input | Expected |
|------|-------|----------|
| WAV → HCA → WAV round-trip | A short synthetic test tone (sine 1 kHz, 44.1 kHz, mono) | Output WAV PSNR ≥ *(threshold, decide in Phase 3)* vs input. Not bit-perfect — HCA is lossy. |
| VGAudio cross-encode | Same input through PyCriCodecsEx vs VGAudio | A/B subjective listen; file size within ~10%. |
| Known-good RE4 HCA decode | A waveform from `core.awb` | Decode matches vgmstream's decode of the same file, sample-for-sample. |

### Phase 4 — Inject (cowbell milestone)

| Target waveform | Replacement | Expected in-game result |
|-----------------|-------------|-------------------------|
| A Leon voice cue from `bio4evt` *(pick a short one — e.g. grunt, hit reaction)* | Cowbell WAV (same channel count, similar length) | Cowbell plays in-game at the moment that cue fires. Verified on Switch hardware or Ryujinx. |
| `bio4bgm` main menu track | A music replacement of similar length | Plays at main menu; loops correctly. Validates ACB `LoopStart`/`LoopEnd` patching. |

### Phase 5 — Inject without AWB rebuild

| Target | Scenario | Expected |
|--------|----------|----------|
| `bio4bgm` waveform | Replacement smaller than original aligned slot | <5s total write time. Audibly correct. Only two offset-table entries touched. |
| `bio4bgm` waveform | Replacement larger than slot | Tool detects and falls back to full rebuild (or refuses, depending on Phase 5 design). |

---

## Known weirdness / gotchas

*(Populate as discovered.)*

- *(e.g.)* "door007 has an unusual cue graph — skip for Phase 2 smoke tests."
- *(e.g.)* "PS4 `bio4midi.acb` mirror field X disagrees with Switch — investigate before Phase 4."

---

## Verification environments

| Env | Purpose | Notes |
|-----|---------|-------|
| Switch hardware | Final ground-truth verification | Requires CFW + LayeredFS for mod-injection tests. |
| Ryujinx | Fast iteration verification | Acceptable proxy for Phase 4 milestone if hardware not available. |
| Clean Windows VM | PyInstaller bundle smoke test | Phase 1 gate — confirm the built binary runs without a Python install. |
