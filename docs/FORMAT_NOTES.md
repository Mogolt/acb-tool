# Format Notes — ACB / AWB / HCA (RE4-relevant parts only)

Concise technical notes scoped to what ACB Tool actually touches. For full format specs, consult the cited sources.

## 1. ACB — `@UTF` table container

### Header

- Magic: `@UTF` — bytes `40 55 54 46` at offset `0x00`.
- Big-endian integers inside the table, despite the file living on a little-endian platform. (`@UTF` tables are BE by the CRI spec.) Confirm in Phase 1; PyCriCodecsEx should abstract this.
- The outer `@UTF` table is the root; it may contain nested `@UTF` blobs as cell values (e.g. the cue table, waveform table, track table).

### Tables relevant to us

- **CueTable** — one row per cue. Columns typically include `CueId`, `CueName` (string reference), `ReferenceType`, `ReferenceIndex`, `UserData`, `Length`, `NumAisacControls`.
- **CueNameTable** — `(CueName, CueIndex)` pairs. **If this table is empty or stripped, the tool loses human-readable names** and the conditional Cue Map tab activates. Phase 1 confirms on `core.acb`.
- **BlockTable / TrackTable / SynthTable / SequenceTable** — the cue graph. We traverse it to reach waveforms; we do not modify it on inject (Phase 4 scope).
- **WaveformTable** — the critical table for injection. Columns include:
  - `Id` — index into the AWB's offset table.
  - `EncodeType` — codec (2 = ADX, 6 = HCA; RE4 uses 6).
  - `Streaming` — 0 = in-memory (rare for RE4), 1 = streamed from AWB (typical).
  - `NumChannels`
  - `SamplingRate`
  - `NumSamples`
  - `LoopStart`, `LoopEnd` — present on looping cues (BGM).

### Per-waveform mirror fields — the inject hazard

`NumSamples`, `LoopStart`, `LoopEnd`, `SamplingRate`, `NumChannels` are **mirrored** in the ACB — the real HCA header in the AWB also carries them, but the engine consults the ACB row at runtime for cue scheduling. Swap a waveform in the AWB for one with different duration and leave the ACB row stale, and the engine mis-schedules: cuts tails, plays garbage past the end, wrong loop points (very audible on BGM), or crashes on pre-allocation.

**Phase 4 requirement:** every inject patches the ACB row in lockstep with the AWB write.

### Sources

- [CriTools ACB parser (JS)](https://github.com/kohos/CriTools/tree/master/acb) — cleanest readable ACB parser.
- [acb.py](https://github.com/summertriangle-dev/acb.py) — Python reference.
- vgmstream [src/meta/acb.c](https://github.com/vgmstream/vgmstream/blob/master/src/meta/acb.c) — C reference; canonical for field names.

---

## 2. AWB — `AFS2` offset-table archive

### Header

- Magic: `AFS2` — bytes `41 46 53 32` at offset `0x00`.
- Little-endian.
- Structure (typical):
  - `0x00` magic `AFS2`
  - `0x04` version / flags (1 byte type, 1 byte offset-size, 1 byte ID-size, 1 padding)
  - `0x08` `file_count` (u32)
  - `0x0C` alignment (u16) — usually `0x20`
  - `0x0E` subkey (u16) — `0x0000` for RE4 (unencrypted)
  - `0x10+` ID table (`file_count` entries of `ID-size` bytes each)
  - followed by offset table (`file_count + 1` entries of `offset-size` bytes each; the last entry is the EOF sentinel)
  - waveform blobs follow, each aligned to `alignment`.

### Inject implications

- **Phase 4 (full rebuild):** rewrite the offset table from scratch after replacing a waveform. Simple, correct, slow on large banks.
- **Phase 5 (in-place):** if the new waveform is ≤ the old one's aligned slot, overwrite in place and only patch that one offset pair — no downstream shift. SonicAudioTools ACB Editor uses this path.

### Sources

- vgmstream [src/meta/awb.c](https://github.com/vgmstream/vgmstream/blob/master/src/meta/awb.c)
- [CriTools AWB parser](https://github.com/kohos/CriTools/tree/master/awb)

---

## 3. HCA — High-Compression Audio (waveform payload)

### Framing

- Self-describing: codec params in the header.
- Header starts with magic `HCA\0` (`48 43 41 00`, possibly with high bit masked as `C8 43 C1 80` in older CRI obfuscation — RE4 is unmasked).
- Header sections (each with its own magic; see vgmstream `hca.c`):
  - `fmt\0` — channel count, sample rate, block count, encoder delay/padding.
  - `comp\0` or `dec\0` — codec parameters.
  - `loop\0` — loop start/end frames *(present on looping cues only)*.
  - `ath\0` — absolute threshold of hearing table flag.
  - `ciph\0` — cipher type. **For RE4: `0` (no encryption). No key setup required.**
  - `rva\0` — relative volume adjustment.
  - `comm\0` — comment string *(rare)*.
- Body: fixed-size frames (usually 0x400 or 0x800 bytes), each decoding to a fixed sample count.

### Relevant to us

- **Decode:** PyCriCodecsEx `HCACodec` handles it; no key passed (RE4 unencrypted). vgmstream is the ground truth for correctness A/B.
- **Encode:** PyCriCodecsEx has an encoder. Phase 3 validates its output against VGAudio reference. If the encoded blob's internal fields (sample rate, channel count, sample count) drift from the WAV input, we propagate those changes into the ACB mirror fields on inject.

### Sources

- vgmstream [src/coding/hca_decoder.c](https://github.com/vgmstream/vgmstream/blob/master/src/coding/hca_decoder.c)
- [VGAudio HCA implementation](https://github.com/Thealexbarney/VGAudio/tree/master/src/VGAudio/Containers/Hca)

---

## 4. Cross-cutting: byte order

- `@UTF` tables: **big-endian** internally.
- AWB header, HCA header, HCA payload: **little-endian** (on both PS4 and Switch).

PyCriCodecsEx abstracts this; only relevant if we hand-parse anything.
