# Phase 0 — Format Report

Ground-truth confirmation of the audio container format used by the 2016 PS4 and 2019 Switch ports of *Resident Evil 4: Ultimate HD Edition* (QLOC).

---

## Switch (2019) — **verified**

Confirmed by direct cartridge dump. Treat as ground truth; no further format discovery required on the Switch side.

### Container

- **Format:** CRIWARE **ADX2** — paired `.acb` (cue/metadata) + `.awb` (waveform archive).
- **Encapsulation:** **none.** Files are loose in the filesystem. No CPK, no Capcom PAK/PCK, no archive wrapper.
- **Encryption:** **none.** HCA waveforms read cleanly without an HCA key. Capcom did not encrypt this release.
- **ACB magic:** `@UTF` (`40 55 54 46`).
- **AWB magic:** `AFS2`.

### `sound/` inventory (partial, from Switch dump)

| Path | Role | PC XACT counterpart |
|------|------|---------------------|
| `foot/` *(subdir)* | Per-surface footstep banks (presumed) | — |
| `room/` *(subdir)* | Per-room ambience banks (presumed) | — |
| `bio4bgm.acb` + `.awb` | Background music | `bio4bgm.xsb`/`.xwb` |
| `bio4evt.acb` + `.awb` | Event SFX | `bio4evt.xsb`/`.xwb` |
| `bio4midi.acb` + `.awb` | Sequenced audio | `bio4midi.xsb`/`.xwb` |
| `core.acb` + `.awb` | Core / UI / system | — |
| `door000.acb`+`.awb` … `door010+` | Per-door sound banks | — |

### Filename convention

Intentionally mirrors the PC version (`bio4evt`, `bio4bgm`, `bio4midi`, …). Strong prior: samples inside Switch ACBs are re-encoded versions of the same samples in the PC XWBs, **in the same order.** This is load-bearing for the fallback cue-name-recovery pipeline (see PLAN.md, conditional Cue Map tab).

### Unknowns to close in Phase 1 (Switch)

- **Cue name presence.** ACB format supports either intact names or stripped tables; QLOC most likely left them intact, but verify on `core.acb` first.

---

## PS4 (2016) — **pending one-minute spot-check**

Zulo: drop the outputs below into this section and I'll fold them in.

### Expected

Identical layout to Switch. Confirming takes ~60 seconds.

### Inputs needed from you

1. **Directory listing of the PS4 sound folder.** Whatever the PS4 equivalent of `sound/` is. `ls -1` output is plenty.
2. **Hex header of one ACB.** e.g.:
   ```
   hexdump -C path/to/core.acb | head
   ```
   First line should start with `40 55 54 46` (`@UTF`). If it doesn't, Capcom did something platform-specific and we'll need to investigate.
3. **Hex header of one AWB.** First 4 bytes should be `41 46 53 32` (`AFS2`).
4. *(Optional but useful)* First 16 bytes of one HCA waveform inside an AWB — confirms unencrypted HCA framing on PS4. Skip if awkward to extract by hand.

### To fill in once provided

- Filesystem layout (expected: matches Switch)
- Magic numbers confirmed
- Encryption status
- Any PS4-only quirks (e.g. byte-order differences — highly unlikely since ADX2 is little-endian on every platform QLOC shipped)

---

## Cross-platform assumptions we're locking in

- **Endianness:** little-endian both platforms.
- **HCA keys:** not needed for RE4 on either console. No HCA key management UI in the tool.
- **ACB/AWB pairing:** by filename stem (`foo.acb` ↔ `foo.awb`).
- **Waveforms external to ACB:** AWB holds the blobs; ACB references them by index. (ADX2 also supports embedded waveforms inside ACB, but RE4 does not use that mode.)

If Phase 0 PS4 spot-check contradicts any of the above, revisit before Phase 1.
