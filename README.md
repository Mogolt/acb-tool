# ACB Studio

GUI tool for extracting and injecting CRIWARE ADX2 audio banks (ACB/AWB) from
the PS4 and Switch ports of **Resident Evil 4**. Drop a replacement WAV on a
cue, save, copy the modified bank onto your console, and hear your audio
in-game.

**Version 2** is a ground-up rewrite in C#/WPF (previously Python/tkinter)
with a fully overhauled interface: sidebar navigation, a Home screen with
plain-language task cards and recent banks, drop-a-file-anywhere routing,
smooth animations throughout, and a single portable EXE instead of an
installer. An **Advanced mode** toggle keeps the default flow simple while
giving power users Quick Extract, waveform internals, and encoder options.
HCA encode/decode now runs on [VGAudio](https://github.com/Thealexbarney/VGAudio)
(the C# reference implementation), which also let two 1.x workarounds
disappear: loop points are set programmatically instead of via the smpl-chunk
injection hack, and the broken upstream smpl parser is no longer in the
pipeline at all. The 1.x Python version lives on in [`legacy/`](legacy/).

## Features

- **Browse** — open an `.acb`, explore cues by name, extract the whole bank
  as named WAV files.
- **Extract** — open an `.awb` directly for quick numbered extraction when you
  don't have or need the ACB.
- **Inject** — queue one or more waveform replacements, auto-resample your
  WAV to the source bank's sample rate, preserve loop points, rebuild the
  AWB, patch the ACB mirror fields + cue lengths, save both files in lockstep.
- **Convert** — standalone WAV ↔ HCA, batch-capable, drag & drop.
- **Audio preview** on every tab: hear a waveform from the bank, or hear your
  replacement WAV before saving. Spot check is a double-click away.

## Supported games

- **Resident Evil 4** — Nintendo Switch (2019) — **verified** (1.x pipeline;
  2.0 produces the same bank layout and passes the same round-trip suite).
- **Resident Evil 4** — PS4 (2016 Ultimate HD Edition) — same bank layout
  expected; light testing.

Other CRIWARE games *may* work — the core layer is format-generic — but only
RE4 is supported and tested. Use on other titles at your own risk.

## Installation

**Windows 10 / 11, x64.**

1. Download `AcbStudio.exe` from the
   [latest release](https://github.com/Mogolt/acb-tool/releases/latest).
2. Run it. Single self-contained EXE — no installer, no .NET required on the
   target machine. Portable by design.

## Usage — minimal inject workflow

1. Rip your own `bio4evt.acb` + `bio4evt.awb` (or whichever bank) from your
   Switch / PS4 install. ACB Studio does not redistribute game data.
2. Open **Inject** tab → *Browse…* → pick your `.acb`. The companion `.awb`
   auto-pairs by filename.
3. Pick the waveform row you want to replace. Double-click (or ♪ **Preview
   source**) to hear it.
4. Click ↻ **Replace with WAV…** and pick your new audio file. Any sample
   rate / channel count works — the tool auto-resamples to match the source
   bank. ♪ **Preview replacement** to A/B.
5. Click ▶ **Save modified bank**. The tool writes a matched pair of modified
   `.acb` + `.awb` with the same filenames.
6. **Switch**: drop both files into
   `atmosphere/contents/<TitleID>/romfs/sound/` via LayeredFS.
   **PS4**: use your preferred file-replacement route.
7. Boot the game. Your audio plays in place of the original.

The loop-aware pipeline keeps BGM and long ambient cues looping seamlessly.
Short SFX and voice lines play cleanly without tail garbage or early cutoff.

## Building from source

Requires the [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0).

```powershell
dotnet build AcbStudio/AcbStudio.csproj            # debug build
dotnet run --project CoreTests/CoreTests.csproj    # round-trip tests
dotnet publish AcbStudio/AcbStudio.csproj -c Release -r win-x64 `
    --self-contained true -p:PublishSingleFile=true   # portable EXE
```

Project layout:

```
AcbStudio/
├── Core/          @UTF parser/serializer, AFS2 archive (KI-001 fixed),
│                  HCA codec via VGAudio, resampler, inject pipeline
├── Services/      audio preview (winmm)
├── ViewModels/    MVVM layer — all app behavior
├── Views/         one XAML view per tab
└── Themes/        dark theme + animated control styles
CoreTests/         43-assertion round-trip suite (AFS2 / @UTF / HCA / inject)
docs/              format notes, phase reports, known issues (still accurate)
legacy/            the original Python/tkinter version (1.x)
```

## Not distributing game files

ACB Studio contains **no** game audio. You must dump your own `.acb` and
`.awb` files from your own legally-owned copy of Resident Evil 4. Don't ask
where to download game banks — the answer isn't here and won't be.

## Credits

- **[VGAudio](https://github.com/Thealexbarney/VGAudio)** by Thealexbarney —
  C# HCA encoder/decoder powering 2.0 (MIT).
- **[vgmstream](https://github.com/vgmstream/vgmstream)** — canonical
  HCA/ADX reference decoder (BSD-3-Clause).
- **[PyCriCodecsEx](https://github.com/mos9527/PyCriCodecsEx)** by mos9527
  and **[PyCriCodecs](https://github.com/Youjose/PyCriCodecs)** by Youjose —
  powered the 1.x Python version (MIT).
- **[SonicAudioTools](https://github.com/blueskythlikesclouds/SonicAudioTools)**
  and **[CriTools](https://github.com/kohos/CriTools)** — ACB/AWB structure
  references.

All attributions also appear in the tool's **?** dialog.

## License

[GPL-3.0-or-later](LICENSE). Copyright © 2026 Mogolt.

## Related projects

- **[XWB Studio](https://github.com/Mogolt/XWB-to-WAV-converter)** — sibling
  project for the XACT (`.xwb`) wave banks used by RE4 2005 PC. Same UX,
  different container family.

## Author

**Mogolt**.
