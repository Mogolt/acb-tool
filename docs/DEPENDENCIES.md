# Dependencies Audit

Updated for v0.1.0 release — all `(verify)` markers resolved. All runtime deps are GPL-3.0 compatible as permissive downstream components (MIT, BSD-3).

## Legend

- **Role:**
  - `depend` — runtime Python dependency, installed via pip.
  - `vendor` — source copied into the repo.
  - `reference` — consulted for format correctness / not linked or shipped.
  - `ignore` — listed for completeness; not used.
- **License column:** attribution required for Inno Setup `LICENSE` panel on any `depend` or `vendor` row.

---

## Runtime dependency

| Name | Repo | License | Role | Version | Install | Concerns |
|------|------|---------|------|---------|---------|----------|
| **PyCriCodecsEx** | [mos9527/PyCriCodecsEx](https://github.com/mos9527/PyCriCodecsEx) | MIT | depend | `0.0.5` | `pip install PyCriCodecsEx==0.0.5` | Load-bearing. `ACB`, `ACBBuilder`, `AWBBuilder`, `HCACodec`, `HCA`. Windows `cp310-win_amd64` wheel available. PyInstaller bundles the C++ `.pyd` cleanly (verified in Phase 1). Known upstream bugs: KI-001 (AWBBuilder off-by-align-block) vendored-fix-applied in `core/awb.py::AWBBuilderFixed`; smpl-chunk WAV parser seek bug bypassed by calling `CriCodecsEx.HcaEncode` directly in `core/hca.py::encode_wav_to_hca_bytes`. |

---

## Reference (not linked, not shipped)

| Name | Repo | License | Role | Used for |
|------|------|---------|------|----------|
| **PyCriCodecs** (upstream) | [Youjose/PyCriCodecs](https://github.com/Youjose/PyCriCodecs) | MIT | reference | Fallback if PyCriCodecsEx has gaps. Upstream of the "Ex" fork. |
| **acb.py** | [summertriangle-dev/acb.py](https://github.com/summertriangle-dev/acb.py) | MIT | reference | Pure-ish Python ACB extractor. Cross-reference only. |
| **vgmstream** | [vgmstream/vgmstream](https://github.com/vgmstream/vgmstream) | BSD-3-Clause | reference | Canonical HCA decoder. Ground truth for extract correctness. RE4 is unencrypted so `hca_keys.h` is not relevant. |
| **VGAudio** | [Thealexbarney/VGAudio](https://github.com/Thealexbarney/VGAudio) | MIT | reference | C# HCA encoder reference. PyCriCodecsEx cleared Phase 3's 40 dB PSNR gate at HIGHEST quality, so pythonnet fallback never landed. |
| **SonicAudioTools** | [blueskythlikesclouds/SonicAudioTools](https://github.com/blueskythlikesclouds/SonicAudioTools) | (see upstream) | reference | C#. Its ACB Editor's "inject without rebuilding AWB" is the pattern for a future Phase 5 on `bio4bgm`-size banks. |
| **CriTools** | [kohos/CriTools](https://github.com/kohos/CriTools) | (see upstream) | reference | JavaScript reference for ACB/AWB structure. Useful cross-read for `@UTF` table layout. |

---

## Explicitly **not** needed (dropped from earlier plan)

| Library category | Why not | Role |
|------------------|---------|------|
| CPK parsers (e.g. CriPakTools) | RE4 console audio is loose in the filesystem, no CPK wrapper. | ignore |
| HCA key management (hca_keys databases, keyfinder tools) | RE4 on Switch is confirmed unencrypted; PS4 expected the same (Phase 0 spot-check). | ignore |
| Capcom PAK/PCK tools | RE4 console audio is loose, no Capcom archive wrapper. | ignore |

---

## Installer LICENSE panel

ACB Tool is distributed under **GPL-3.0**. The installer's License page at
`packaging/LICENSE.txt` shows: GPL-3.0 summary + pointer to the full text at
the repo root, plus attributions for PyCriCodecsEx / PyCriCodecs / vgmstream /
VGAudio. All bundled dependencies are MIT or BSD-3-Clause, so there's no
conflict with the GPL-3.0 outer license.
