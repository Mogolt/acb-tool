# ACB Tool

GUI tool for extracting and injecting CRIWARE ADX2 audio banks (ACB/AWB) from
the PS4 and Switch ports of **Resident Evil 4**. Drop a replacement WAV on a
cue, save, copy the modified bank onto your console, and hear your audio
in-game.

## Features

- **Browse** — open an `.acb`, explore cues by name, extract the whole bank
  as named WAV files.
- **Extract** — open an `.awb` directly for quick numbered extraction when you
  don't have or need the ACB.
- **Inject** — queue one or more waveform replacements, auto-resample your
  WAV to the source bank's sample rate, preserve loop points, rebuild the
  AWB, patch the ACB mirror fields + cue lengths, save both files in lockstep.
- **Convert** — standalone WAV ↔ HCA, batch-capable.
- **Audio preview** on every tab: hear a waveform from the bank, or hear your
  replacement WAV before saving. Spot check is a double-click away.

## Supported games

- **Resident Evil 4** — Nintendo Switch (2019) — **verified**.
- **Resident Evil 4** — PS4 (2016 Ultimate HD Edition) — same bank layout
  expected; light testing.

Other CRIWARE games *may* work — the core layer is format-generic — but only
RE4 is supported and tested. Use on other titles at your own risk.

## Installation

**Windows 10 / 11, x64.**

1. Download `ACB_Tool_Setup.exe` from the
   [latest release](https://github.com/Mogolt/acb-tool/releases/latest).
2. Run it. Standard installer wizard — accept the GPL-3.0 license, pick an
   install path (default `C:\Program Files\ACB Tool`), optionally create a
   desktop shortcut.
3. Launch from the Start menu.

To uninstall, use Add/Remove Programs — everything including the Start menu
entry goes away cleanly.

## Usage — minimal inject workflow

1. Rip your own `bio4evt.acb` + `bio4evt.awb` (or whichever bank) from your
   Switch / PS4 install. ACB Tool does not redistribute game data.
2. Open **Inject** tab → *Browse…* → pick your `.acb`. The companion `.awb`
   auto-pairs by filename.
3. Pick the waveform row you want to replace. Click ♪ **Preview source** to
   hear it.
4. Click ↻ **Replace with WAV…** and pick your new audio file. Any sample
   rate / channel count works — the tool auto-resamples to match the source
   bank. Click ♪ **Preview replacement** to A/B.
5. Click ▶ **Save modified bank**. The tool writes a matched pair of modified
   `.acb` + `.awb` with the same filenames.
6. **Switch**: drop both files into
   `atmosphere/contents/<TitleID>/romfs/sound/` via LayeredFS.
   **PS4**: use your preferred file-replacement route.
7. Boot the game. Your audio plays in place of the original.

The loop-aware pipeline keeps BGM and long ambient cues looping seamlessly.
Short SFX and voice lines play cleanly without tail garbage or early cutoff.

## Not distributing game files

ACB Tool contains **no** game audio. You must dump your own `.acb` and
`.awb` files from your own legally-owned copy of Resident Evil 4. Don't ask
where to download game banks — the answer isn't here and won't be.

## Credits

- **[PyCriCodecsEx](https://github.com/mos9527/PyCriCodecsEx)** by mos9527 —
  Python library for CRIWARE ACB/AWB/HCA read + write (MIT).
- **[PyCriCodecs](https://github.com/Youjose/PyCriCodecs)** by Youjose —
  upstream of PyCriCodecsEx (MIT).
- **[vgmstream](https://github.com/vgmstream/vgmstream)** — canonical
  HCA/ADX reference decoder (BSD-3-Clause).
- **[VGAudio](https://github.com/Thealexbarney/VGAudio)** by Thealexbarney —
  HCA encoder reference (MIT).

All attributions also appear in the tool's **? → About** dialog.

## License

[GPL-3.0-or-later](LICENSE). Copyright © 2026 Mogolt.

Bundled dependencies retain their own MIT / BSD-3 licenses; see
[docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).

## Author

**Mogolt**.
