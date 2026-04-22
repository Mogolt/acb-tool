# Phase 1 — PyCriCodecsEx De-risk

**Date:** 2026-04-22
**Status:** ✅ PASS. Risk register item *"PyCriCodecsEx has no Windows wheel / fails under PyInstaller"* is closed.

---

## 1. Install — clean

```
.venv/Scripts/python -m pip install PyCriCodecsEx
  → Downloading pycricodecsex-0.0.5-cp310-cp310-win_amd64.whl (81 kB)
  → Successfully installed PyCriCodecsEx-0.0.5
```

- **Prebuilt Windows wheel exists** for Python 3.10 (`cp310-win_amd64`). No local C++ compile step required.
- Single dependency, no transitive pip churn.
- `__version__ = "0.0.5"`.

## 2. Python import surface — complete

All classes referenced in PLAN.md `core/` stubs are present and callable:

| Submodule | Classes verified |
|-----------|------------------|
| `PyCriCodecsEx.acb` | `ACB`, `ACBBuilder`, `ACBTable`, `CueTable`, `CueNameTable` |
| `PyCriCodecsEx.awb` | `AWB`, `AWBBuilder`, `AWBChunkHeader`, `AWBType` |
| `PyCriCodecsEx.hca` | `HCA`, `HCACodec`, `HcaAthHeaderStruct`, `HcaCiphHeaderStruct` |
| `PyCriCodecsEx.utf` | `@UTF` table primitives |

Note: the top-level `PyCriCodecsEx` package does not re-export anything — `__init__.py` is just `__version__ = "0.0.5"`. All user-facing classes live in submodules (`PyCriCodecsEx.acb`, `.awb`, `.hca`, `.utf`, `.adx`, `.cpk`, `.usm`). Import them directly.

## 3. C++ backend

- File: `.venv/lib/site-packages/CriCodecsEx.cp310-win_amd64.pyd` (top-level, not inside the package).
- Backend symbols: `HcaDecode`, `HcaEncode`, `HcaCrypt`, `AdxDecode`, `AdxEncode`, `CriLaylaCompress`, `CriLaylaDecompress`.
- `HcaCrypt` is present — confirms encryption support exists in the library even though RE4 doesn't use it.

## 4. PyInstaller bundle — works

```
.venv/Scripts/python -m PyInstaller --onefile packaging/smoke_test.py
  → packaging/dist/smoke_test.exe (5.6 MB)
```

Execution from a shell with **PATH scrubbed to `C:/Windows/System32:C:/Windows` only** (no venv, no system Python on path):

```
$ ./packaging/dist/smoke_test.exe
OK
  ACB        : <class 'PyCriCodecsEx.acb.ACB'>
  ACBBuilder : <class 'PyCriCodecsEx.acb.ACBBuilder'>
  AWB        : <class 'PyCriCodecsEx.awb.AWB'>
  AWBBuilder : <class 'PyCriCodecsEx.awb.AWBBuilder'>
  HCA        : <class 'PyCriCodecsEx.hca.HCA'>
  HCACodec   : <class 'PyCriCodecsEx.hca.HCACodec'>
  CriCodecsEx: <user-temp>\_MEI<random>\CriCodecsEx.cp310-win_amd64.pyd
exit: 0
```

PyInstaller auto-detected the top-level `.pyd` and extracted it to its `_MEI*` temp dir at runtime. **No custom hook needed.** No missing DLL warnings in `warn-smoke_test.txt` (checked).

## 5. Implications

- Phase 4 / packaging is green-lit. Final installer will work without a Python install on the target machine.
- `acb_tool.spec` in `packaging/` can be regenerated from the smoke-test spec (or hand-rolled later; the defaults are fine for now).
- The `requirements.txt` pin can now be hardened to `PyCriCodecsEx==0.0.5`.

## 6. What's **not** covered by this de-risk

These remain as Phase 1 sub-tasks:

- Opening a real `core.acb` / `core.awb` from the Switch dump and dumping its structure (cue names presence question).
- PC↔console waveform correspondence check on `bio4evt` (needs PC CSV from zulo).
- Extract-all + re-inject round-trip byte-comparison.
- Test corpus hashing for the Phase 1 golden set.

All four are blocked on test files, not on library capability.

---

## Artifacts produced

- `packaging/smoke_test.py` — the smoke-test source.
- `packaging/smoke_test.spec` — PyInstaller spec generated automatically.
- `packaging/dist/smoke_test.exe` — the 5.6 MB frozen binary that proved bundling works.
- `packaging/build/` — PyInstaller intermediates (safe to delete; regenerated on next build).

## Next action (awaiting you)

Provide path to the Switch `sound/` dump (specifically `core.acb` + `core.awb`) so the next de-risk step — opening real ADX2 data — can run.
