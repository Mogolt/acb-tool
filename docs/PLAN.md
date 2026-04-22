# ACB Tool — Architectural Plan

**Status:** planning complete, awaiting your sign-off before Phase 1.

---

## 1. Goal

Ship a Windows desktop utility, visually and technically sibling to **XWB Tool**, that extracts and injects CRIWARE ADX2 audio (`.acb` + `.awb`) from the 2016 PS4 and 2019 Switch ports of Resident Evil 4.

Primary success metric: **Phase 4 milestone** — replacing Leon's grunt with a cowbell and hearing the cowbell in-game on real Switch hardware or Ryujinx.

---

## 1a. Schedule amendment (2026-04-22) — Quick Mode shipped early

**What moved:** Quick Extract mode (the AWB-only path from the two-mode design in §3) was implemented ahead of schedule as "Phase 2 Quick Mode, shipped early." The Extract tab now opens an `.awb`, lists waveforms with channels / sample-rate / duration / sample-count, and extracts all tracks to numbered WAV files via PyCriCodecsEx. The other three tabs (Browse / Inject / Convert) remain placeholder frames.

**Why:** gives the tester a runnable exe to exercise on real Switch `.awb` files immediately, and de-risks the AWB read path + PyCriCodecsEx `HCACodec.save()` surface well before the rest of Phase 2 begins.

**Artifacts:** first one-folder PyInstaller build at `packaging/dist/ACB Tool/`, zipped to `packaging/dist/ACB_Tool.zip` (~8 MB compressed, ~19 MB uncompressed, 939 files). Backend `.pyd` bundles cleanly at `_internal/CriCodecsEx.cp310-win_amd64.pyd`.

**Effect on phase gates:** Phase 2's gate (Browse tab + cue-tree + named extraction) is unchanged — this early shipment delivers only the Quick Mode half. The Full Project half remains the Phase 2 deliverable.

---

## 2. Finalized decisions

| Question | Decision | Rationale |
|---|---|---|
| Name | **ACB Tool** | Mirrors "XWB Tool" directly; reads as a technical sibling. |
| Platform | **Windows-only** | Matches XWB Tool. PyInstaller + Inno Setup. Keeps the PyCriCodecsEx C++ backend story to one wheel target. Linux can be added post-Phase 5 without a rewrite if we keep core platform-neutral. |
| Repo organization | **Standalone repo, standalone brand** | Keeps XWB Tool untouched during ACB bring-up. Merge deferred until both sides are stable and a format-agnostic core is designed deliberately. |
| Interfaces | **GUI-only** Phases 0–5 | Fastest path to the cowbell milestone. CLI deferred to Phase 6+ once core API stabilizes. |
| PyCriCodecsEx | **Hard dependency**, no fallback abstraction | Validate in Phase 1 spike. If it fails, pivot then. Avoid YAGNI abstractions for hypothetical failure. |

---

## 3. Architecture

### Package layout

Departure from XWB Tool's single-file monolith — ACB/AWB injection has materially more moving parts (ACB mirror-field patching, AWB offset-table rebuild, HCA encode), and a clean split pays for itself by Phase 4.

- **`core/`** — dataclasses (`Cue`, `Waveform`, `Bank`, `Project`), PyCriCodecsEx wrapper, codec adapters. **No tkinter imports.** Platform-neutral.
- **`gui/`** — `App(tk.Tk)` shell + per-tab modules. Owns all tk/ttk imports.
- **`acb_tool.py`** — entry point (calls `gui.app.main()`).

### Two-mode design

Mode split reflects the ACB-coupling reality (read-only is cheap; write requires both files).

| Mode | Entry | Read ACB? | Cue names? | Writable? | Use case |
|------|-------|-----------|------------|-----------|----------|
| **Quick Extract** | drag AWB or "Open AWB" | no | no (`track_000.wav`, …) | no | casual "what's in this file" exploration |
| **Full Project** | "Open ACB" (auto-pairs AWB by stem) | yes | yes (assumed — verify Phase 1) | yes | primary modding workflow |

Both modes share the `core/` backend; they differ only in GUI entry points.

### GUI tabs

Mirrors XWB Tool's tabbed layout, adapted for ADX2 semantics.

1. **Browse** — two entry paths (Open ACB / Open AWB). Project mode shows cue tree + waveform list; Quick mode shows numbered waveforms.
2. **Extract** — bulk WAV out, optional raw `.hca` passthrough, progress bar. Project mode names files from cues; Quick mode uses indices.
3. **Inject** — Project mode only. Pick waveform → browse replacement `.wav` → encode → rebuild AWB → patch ACB mirror fields. Phase 4 ships full rebuild; Phase 5 adds inject-without-rebuild.
4. **Convert** — standalone WAV ↔ HCA, batch-capable, mode-independent.
5. **Cue Map** *(conditional)* — kept **only if** Phase 1 finds cue names stripped. Handles the "match against PC XWB extracts" fallback to bootstrap names from XWB Tool's bank. **Default plan: this tab is cut.**

### Visual language (mirror verbatim from XWB Tool)

- Palette: `BG=#1a1a2e, PANEL=#16213e, ACCENT=#e94560, TEXT=#eaeaea, MUTED=#7a7a9a, SUCCESS=#4ecca3, WARNING=#f5a623`
- Fonts: Consolas 9/10/13
- ttk theme: `clam`, custom Progressbar (`troughcolor=PANEL, background=ACCENT`)
- Tab underline: thin accent `Frame` under the active tab label
- `_folder_row()` helper (XWB Tool ~lines 1850–1865)
- `recent_folders.json` persistence (XWB Tool ~lines 1873, 1889)

### Concurrency pattern (mirror verbatim)

```python
threading.Thread(target=_work, daemon=True).start()
# _work updates GUI via self.after(0, lambda: ...)
# Cancellation via self._stop_event.is_set()
```

### Drop from XWB Tool

- Hardcoded per-user `...\Python310\python.exe` auto-relaunch (ship with bundled interpreter only).
- Krita ffmpeg PATH injection (not needed without AudioSR in Phase 0–5).

### Packaging

- PyInstaller one-folder build matching XWB Tool.
- Inno Setup installer, `LICENSE` panel lists PyCriCodecsEx attribution.
- Verify in Phase 1 that PyInstaller bundles PyCriCodecsEx's `.pyd` correctly.

---

## 4. Phased roadmap

Each phase ends with in-game verification before the next begins.

| Phase | Deliverable | Gate | Rough effort |
|-------|-------------|------|---|
| **0** | PS4 spot-check: you provide hexdump + listing, I fold into `PHASE_0_FORMAT_REPORT.md` | PS4 section of format report complete | <1 hour (mostly waiting on you) |
| **1** | Spike: install PyCriCodecsEx, open `core.acb/awb`, dump structure, verify cue names present, **PC↔console waveform-correspondence check on `bio4evt` (see §4a)**, extract all waveforms as WAV, re-inject same bytes, confirm round-trip byte-identical (or identify tolerable drift). Verify PyInstaller bundles the C++ backend. | Round-trip works; PyInstaller build runs on a clean VM; correspondence check documented | 1–2 days |
| **2** | Browse + Extract for both modes. Tests against PS4 and Switch dumps. | **From cold start: open any RE4 Switch ACB via Browse tab, see the full cue tree with names, select-all → extract entire bank to named WAVs in one click, no tracebacks or silent failures. Quick Extract works the same way on a raw AWB. Both modes pass against at least three banks (`core`, `bio4evt`, one `doorNNN`).** | 3–5 days |
| **3** | Convert tab (WAV ↔ HCA). Encode validated in isolation against vgmstream ground truth. | **PSNR ≥ 40 dB across a 10-sample corpus (mix of speech, SFX, music drawn from `core.awb` and `bio4bgm.awb`) AND no audible artifacts in a manual A/B listen at listening volume. Per-sample PSNR logged in `docs/phase3_encoder_validation.md` as a baseline for future encoder changes. If PyCriCodecsEx fails to clear 40 dB, pivot to the VGAudio-via-pythonnet fallback from the risk register — don't lower the bar.** | 2–3 days |
| **4** | Inject with full AWB rebuild + ACB mirror patch. **Cowbell milestone.** | Cowbell audible in-game on Switch hardware or Ryujinx | 4–7 days |
| **5** | Inject without AWB rebuild (SonicAudioTools pattern). Important for `bio4bgm`-size banks. | `bio4bgm` injection completes in <5s per-waveform on a typical SSD | 3–5 days |
| **6+ (deferred)** | AI Remaster tab (mirrors XWB Tool), CLI, eventual merge with XWB Tool | — | — |

### 4a. Phase 1 sub-task — PC↔console waveform correspondence

Inserted between the cue-name verification and the round-trip test. ~10 minutes of work; meaningful insurance on two downstream decisions.

**Action:** extract waveform count and durations from `bio4evt.acb` (Switch) and compare against `bio4evt.xwb` (RE4 PC, 2005). Zulo provides a CSV of PC indices + durations on request.

**Pass criterion:** counts match; per-waveform durations within ~1% tolerance.

**Why it matters:**
- **If pass:** the PC↔console filename mirror holds at the *content* level, not just the naming level. This unlocks the Cue Map "match against PC XWBs" fallback as a viable name-recovery path if cue names are ever stripped, and gives high confidence that existing RE4 PC modding knowledge transfers to the console tool.
- **If fail:** QLOC reorganized banks during the port. That's load-bearing information — FORMAT_NOTES.md and the Cue Map fallback design both need revision before Phase 2.

**Documented in:** `docs/pc_console_correspondence.md` (created in Phase 1).

---

## 5. Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| PyCriCodecsEx has no Windows wheel / fails under PyInstaller | Low-Medium | High (blocks Phase 4) | Confirm in Phase 1 day 1. Fallback: vendor the C++ backend and build it locally; worst case pivot to PyCriCodecs upstream + acb.py for read + VGAudio via pythonnet for write. |
| ACB mirror-field coverage incomplete — some field drifts and we don't catch it | Medium | Medium (audio glitches in-game, but debuggable) | Phase 1 round-trip test compares every field pre/post. Phase 4 manual A/B against vgmstream decode. |
| Cue names stripped in RE4 ACBs | Low | Low (forces Cue Map tab back into scope) | Phase 1 finding — deterministic cost of adding the tab if needed. You already have PC XWB extracts to match against. |
| HCA encoder quality from PyCriCodecsEx inferior to VGAudio | Low | Medium (audible artifacts) | Phase 3 validation against VGAudio reference encode. If inferior: shell out to VGAudio via pythonnet, or accept the quality gap. |
| Switch and PS4 diverge in ACB version / field layout | Low | Medium | Phase 0 spot-check catches gross divergence. Phase 2 tests both platforms explicitly. |

---

## 6. What's out of scope (permanently, for this tool)

- RE4 Remake (2023) — RE Engine + Wwise.
- RE4 PS3 / Xbox 360 (2011 HD).
- Xbox One UHD — free win if the spot-check shows it matches PS4, otherwise ignored.
- CPK archive handling (RE4 console audio is loose).
- HCA key management UI (RE4 is unencrypted).
- Non-RE4 CRIWARE games — code kept clean enough that pointing it at Persona 5 Royal *might* work, but we validate only against RE4.

---

## 7. Reference files

- **XWB Tool source:** `xwb_tool.py` (external; not redistributed)
  - Color palette: ~lines 672–680
  - `_folder_row()`: ~lines 1850–1865
  - Threading pattern example: ~line 1268
  - Recent folders persistence: ~lines 1873, 1889
  - PyInstaller docstring: ~line 6
- **Switch RE4 `sound/` dump** — Phase 1 test corpus source
- **PS4 RE4 dump** — pending from you, Phase 0 input
