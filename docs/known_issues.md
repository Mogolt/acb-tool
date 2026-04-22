# Known Issues

## KI-002: xwb_to_csv.exe tries to locate xwb_tool.py at runtime

**Discovered:** 2026-04-22 (zulo, during Phase 2 → Phase 3 handoff).
**Severity:** Low. **Status:** deferred — correspondence check abandoned; Phase 2 already answered the underlying question.

The frozen `xwb_to_csv.exe` bundles `xwb_tool` via `--hidden-import`, but the script's `_locate_xwb_tool()` still does runtime path discovery (env var → `../../xwb_tool.py` relative to the script). On a machine that doesn't have `xwb_tool.py` on disk, the lookup fails even though the imported module is available in the PyInstaller bundle.

**Fix (when we come back to it):** swap `_locate_xwb_tool()` + `sys.path.insert()` for an unconditional top-level `import xwb_tool`. PyInstaller's static analysis will pick up the module, and runtime disk presence becomes irrelevant. Drop the `XWB_TOOL_PATH` env-var hook if it was never used.

---

## KI-001: PyCriCodecsEx AWBBuilder over-pads when header size is already aligned

**Status: RESOLVED (2026-04-22) via Option 3 (vendored fix).**
**Fix site:** `core/awb.py::AWBBuilderFixed` + `rebuild_awb_bytes()`.
**Regression test:** `scripts/test_awb_roundtrip.py` — four assertions, all pass: KI-001 minimal repro, `core.awb` round-trip, `door003.awb` round-trip, and full WAV → HCA → AWB → re-extract → decode ≥ 40 dB PSNR. Rebuilt `core.awb` and `door003.awb` are byte-identical in size to their sources.

During the fix a **second bug** surfaced: upstream's offset-table math derives `ofs[i]` from cumulative RAW payload sizes while the write loop adds per-blob alignment padding. Those drift apart the moment any blob length isn't a multiple of `align` — which every RE4 HCA blob is. The vendored `build()` sidesteps both by simulating the write sequence directly and snapshotting `out.tell()` at each blob boundary.

---

### Original report (kept for historical context)

**Discovered:** 2026-04-22 during synth-test chase before Phase 2 Full Project.
**Severity when open:** Medium. Blocked Phase 4 Inject full-rebuild path.
**Affected real-game extraction (Phase 1/2 read path):** No. We used `AWB()` (reader), not `AWBBuilder()` (writer), for extraction.
**Upstream:** [mos9527/PyCriCodecsEx](https://github.com/mos9527/PyCriCodecsEx), version `0.0.5` (`.venv/lib/site-packages/PyCriCodecsEx/awb.py`, line ~143).

### Symptom

Feeding any two HCA blobs through `AWBBuilder([hca, hca]).build()` and reading the result back with `AWB(...)` yields garbage starting at waveform 2. Waveform 1 looks valid by luck (extra padding gets tacked onto the end of its decode buffer, which HCA decoders ignore). Waveform 2 is read from the wrong offset and the read is also short of the true waveform-2 end.

### Minimal repro (< 10 lines)

```python
from PyCriCodecsEx.awb import AWB, AWBBuilder

payload = b'HCA\x00' + b'\xAA' * 60           # 64 bytes, len % align (32) == 0
awb_bytes = AWBBuilder([payload, payload]).build()

awb = AWB(awb_bytes)
print(awb.get_file_at(0)[:4])   # b'HCA\x00' by luck
print(awb.get_file_at(1)[:4])   # b'\xaa\xaa\xaa\xaa' — bug
```

Trigger condition: `(16 + id_intsize*numfiles + offset_intsize*(numfiles+1)) % align == 0`. With default settings (`id_intsize=2, offset_intsize=4, align=32`) this fires whenever `numfiles ∈ {2, 5, 10, 13, 18, 21, …}` — i.e. very often in practice.

### Root cause

`PyCriCodecsEx/awb.py` around line 143:

```python
headersize = len(header) + intsize * numfiles + intsize
aligned_header_size = headersize + (self.align - (headersize % self.align))
```

No guard for `headersize % align == 0`. When the header is already aligned, `self.align - 0 == self.align`, so a full extra alignment block is added to `aligned_header_size`. All subsequent waveform offsets are then written into the file shifted by `align` bytes past where the payloads were actually placed, while the physical header written to disk is still only `headersize` long (lines ~156–157 correctly skip the ljust when already aligned).

Reader (`AWB._readheader`) aligns offsets up defensively:
```python
self.ofs.append(i[0] if i[0] % self.align == 0 else (i[0] + (self.align - (i[0] % self.align))))
```
That's a no-op here because the builder already wrote aligned-up offsets. The reader trusts the offset table, so it reads from wrong positions.

### Why real-game AWBs read correctly despite this bug

Real Switch RE4 `.awb` files were built by CRI's official tools, not PyCriCodecsEx. Their offset tables are internally consistent, so `AWB().get_file_at(i)` returns correct blobs and Quick Mode extraction works end-to-end (verified cross-machine). The bug only manifests when **we** call `AWBBuilder` ourselves — which Phase 1/2 never does.

### Impact on Phase 4 (Inject, full AWB rebuild)

Phase 4 replaces one waveform, then calls `AWBBuilder(new_waveform_list).build()`. If the resulting header size happens to fall on an alignment boundary, the rebuilt AWB will have shifted offsets and the in-game audio will play garbage or crash. We must fix this before Phase 4 ships.

### Options (pick before Phase 4)

1. **Upstream patch.** One-liner in `PyCriCodecsEx/awb.py`:
   ```python
   aligned_header_size = headersize if headersize % self.align == 0 \
       else headersize + (self.align - (headersize % self.align))
   ```
   PR to mos9527/PyCriCodecsEx. Clean. Dependency on merge + release timeline.

2. **Monkey-patch at startup in `core/awb.py`.** Replace `AWBBuilder.build` with a fixed version at import time. No upstream wait, but we carry the patch forever.

3. **Vendor a fixed `AWBBuilder` inside `core/awb.py`.** Forks the ~40-line method. Clearest provenance; easiest to audit.

4. **Avoid full-rebuild entirely.** Phase 5's inject-without-rebuild path (SonicAudioTools pattern) sidesteps `AWBBuilder` completely by doing in-place offset patching. If we ship Phase 5 before Phase 4, this bug never bites us. Plausible but reorders the phased roadmap.

**Recommendation:** send upstream patch (Option 1) in parallel; implement Option 3 (vendored fix) in `core/awb.py` as the default path for Phase 4 so we don't depend on upstream release timing. Revisit if upstream merges quickly.

### Test coverage to add when Phase 4 lands

- Round-trip: build AWB from N synthetic HCAs for each N in `{1, 2, 3, 5, 10, 13}` (mix of triggering and non-triggering numfiles), read back, verify each `get_file_at(i)[:4] == b'HCA\0'` (or encrypted variant).
- Round-trip on a real Switch bank: extract → rebuild → extract again → byte-compare the round-tripped WAVs.

### Time spent on diagnosis

~45 minutes. Well under the 1-day budget. Proceeding to Phase 2 Full Project.
