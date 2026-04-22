# Phase 2 — ACB Structure Report

Structural analysis of RE4 Switch `.acb` files for Phase 2 Full Project mode. Source: Switch cartridge dump, files at `test_files/switch/`. Parsing done with `PyCriCodecsEx.acb.ACB` (version 0.0.5).

**TL;DR:** Cue names are 100% intact across all tested banks — **Cue Map tab stays cut**. Schema varies across banks, so the reader must handle two waveform-field layouts and at least two cue reference types.

---

## Format baseline

| Field | Value |
|-------|-------|
| ACB format version | `1.16.01 PC Format` (raw value `0x01160100` = 18219264) |
| `@UTF` endianness | big-endian tables, little-endian file container |
| Embedded `AwbFile` | 0 bytes in all tested banks → waveforms live in external `.awb` only |
| Encode type for all waveforms | `HCA` (`AcbEncodeTypes.HCA = 2`) |
| Streaming flag | 1 for every waveform → external AWB confirmed |

Capcom left cue names intact. QLOC also left the whole cue graph alone — we can resolve cues → waveforms without needing XWB fallback.

---

## Per-bank summary

| Bank | Cues | Names | Waveforms | CueTable refType | WaveformTable fields |
|------|-----:|------:|----------:|:----------------:|:--------------------|
| `core`    |  65 |  65 |  65 | `0x01` only | `Id`, `EncodeType`, `NumChannels`, `SamplingRate`, `NumSamples`, `LoopFlag`, `Streaming`, `ExtensionData` |
| `door003` |   2 |   2 |   2 | `0x01` only | same as `core` |
| `bio4evt` | 281 | 281 | 281 | `0x03` only | `MemoryAwbId`, `StreamAwbId`, `StreamAwbPortNo`, `EncodeType`, `NumChannels`, `SamplingRate`, `NumSamples`, `LoopFlag`, `Streaming`, `ExtensionData` |

**Empty cue names across all banks: 0.** Every cue has a human-readable name.

**Example cue names (from `core`):** `ItemGet_18k`, `ItemGet_18k_1`, `cersol`, `cersol_1`, `cersol_2`, `dami`, `dami_1`, `dami_2`, `dial`, `gold_0713`, `hazusu`, `hazusu_1`, `itemget_fixeq2`.

Naming convention suggests a mix of Japanese romaji and English functional labels — typical Capcom style. Output WAVs will be very readable.

---

## Schema divergence — two waveform layouts

### Simple schema (`core`, `door003`)

WaveformTable has a single `Id` field that doubles as the AWB offset-table index:

```
EncodeType, Id, NumChannels, SamplingRate, NumSamples, LoopFlag, Streaming, ExtensionData
```

### Extended schema (`bio4evt`)

WaveformTable has separate `MemoryAwbId` and `StreamAwbId` fields. With `Streaming=1`, the `StreamAwbId` is the AWB-file index; `MemoryAwbId` is `0xFFFF` (unused):

```
EncodeType, MemoryAwbId, StreamAwbId, StreamAwbPortNo, NumChannels, SamplingRate, NumSamples, LoopFlag, Streaming, ExtensionData
```

### Resolver rule

```
if 'StreamAwbId' in payload and Streaming == 1:
    awb_index = StreamAwbId
elif 'MemoryAwbId' in payload:
    awb_index = MemoryAwbId   # only seen in non-streaming banks
elif 'Id' in payload:
    awb_index = Id            # simple schema
else:
    hard error — unknown schema
```

Implemented in `core/acb.py::Waveform.from_acb_entry`.

---

## Schema divergence — two cue reference types

### `refType = 0x01` — direct (`core`, `door003`)

`CueTable.ReferenceIndex` is the WaveformTable index directly. One cue, one waveform.

### `refType = 0x03` — sequence (`bio4evt`)

`CueTable.ReferenceIndex` is a `SequenceTable` index. The sequence holds `NumTracks` big-endian `uint16` waveform indices in `TrackIndex`. In `bio4evt` every sequence has `NumTracks=1`, so it's effectively also one cue → one waveform, just with an extra layer of indirection.

### Reference types seen but not yet handled

`0x02` (Synth) and `0x08` (BlockSequence) are defined in PyCriCodecsEx but not seen in any of the three RE4 banks tested. If a future bank has them, the reader should degrade gracefully (surface a `SynthNotImplemented` label rather than crash).

---

## PyCriCodecsEx interop notes

The upstream `.cues` helper on `ACB` hardcodes `.MemoryAwbId` access and therefore **throws on `core` and `door003`** (simple schema) while working on `bio4evt`. We cannot rely on it. Our `core/acb.py` resolves cue → waveform → AWB index directly off the `_payload` dict, handling both schemas.

Upstream's `_waveform_of_sequence` at line 108 also yields `WaveformTable[track_index]` directly, which assumes TrackIndex holds waveform indices. For RE4 `bio4evt` this happens to be true (each "sequence" is a single-track direct pointer), but the code name suggests it should go through TrackTable/TrackEventTable. We reproduce the observed behavior for now and add a TODO if a bank breaks the assumption.

---

## Field table reference for Phase 4 inject

For the ACB-mirror-field patching required by Phase 4, these are the fields per waveform that must be kept consistent with the replacement HCA header:

| Field | Source of truth | Phase 4 action on inject |
|-------|-----------------|--------------------------|
| `NumChannels` | replacement WAV | write it (abort if mismatch) |
| `SamplingRate` | replacement WAV | write it (abort if mismatch) |
| `NumSamples` | PyCriCodecsEx `HCACodec.total_samples` after encode | write it |
| `LoopFlag` | replacement WAV `smpl` chunk | write it |
| `StreamAwbId` / `MemoryAwbId` / `Id` | identity (same as before) | untouched |
| `EncodeType` | identity (`HCA = 2`) | untouched |
| `Streaming` | identity | untouched |

Cue-level `CueTable.Length` (ms) — PyCriCodecsEx's own docstring says "Cue duration is not set. You need to change that manually — this is usually unnecessary as the player will just play until the end of the waveform." We treat this as optional-to-update and revisit if Phase 4 test on hardware shows audible truncation.

---

## Sources

- PyCriCodecsEx `acb.py` (`ACBTable`, `_waveform_of_*` helpers) — reference for TLV decoding.
- vgmstream `src/meta/acb.c` — canonical field names.
- This analysis: `test_files/switch/{core,bio4evt,door003}.{acb,awb}` from Switch cartridge dump, 2026-04-22.
