"""Dump XWB track metadata to CSV for the Phase 1 PC<->console correspondence check.

One-off tooling. Does NOT ship in the installer. Reuses XWB Tool's existing
`_parse_xwb_tracks` parser verbatim \u2014 no reimplementation.

Usage:
    python xwb_to_csv.py path/to/bio4evt.xwb
    python xwb_to_csv.py path/to/bio4evt.xwb -o bio4evt_pc.csv

CSV columns (one row per waveform, in bank order):
    index,duration_seconds,sample_count,sample_rate,channels,codec

Notes:
  - PC XWB sample_count is derived as round(duration_seconds * sample_rate).
    Exact for PCM and ADPCM, which is what RE4 PC (2005) uses in practice.
  - For XMA/WMA the XWB parser does not compute duration; those rows emit
    empty duration_seconds and sample_count cells so the discrepancy is
    visible rather than silently zero.
  - Requires Python 3.10 (same as XWB Tool).
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path


def _locate_xwb_tool() -> Path:
    """Find xwb_tool.py so we can import its parser.

    Resolution order:
      1) ``$XWB_TOOL_PATH`` env var (if set and points to an existing file)
      2) ``../../xwb_tool.py`` relative to this script — i.e. place xwb_tool.py
         in the parent-of-parent directory (typically the folder that contains
         this tool's repo clone).
    """
    env = os.environ.get("XWB_TOOL_PATH")
    if env and Path(env).is_file():
        return Path(env)

    here = Path(__file__).resolve().parent
    candidate = here.parent.parent / "xwb_tool.py"
    if candidate.is_file():
        return candidate

    raise FileNotFoundError(
        "Could not locate xwb_tool.py. Set XWB_TOOL_PATH or place it at "
        "../../xwb_tool.py relative to this script."
    )


def _load_xwb_tool():
    path = _locate_xwb_tool()
    sys.path.insert(0, str(path.parent))
    import xwb_tool  # noqa: E402  (deferred import by design)
    return xwb_tool


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dump XWB track metadata to CSV.")
    ap.add_argument("xwb", help="Path to the .xwb file")
    ap.add_argument("-o", "--output", help="Write CSV here (default: stdout)")
    args = ap.parse_args(argv)

    xwb_path = Path(args.xwb)
    if not xwb_path.is_file():
        print(f"error: not a file: {xwb_path}", file=sys.stderr)
        return 2

    xwb_tool = _load_xwb_tool()
    tracks = xwb_tool._parse_xwb_tracks(str(xwb_path))

    out_stream = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
    try:
        w = csv.writer(out_stream)
        w.writerow(["index", "duration_seconds", "sample_count", "sample_rate", "channels", "codec"])
        for t in tracks:
            rate = int(t.get("rate", 0))
            dur  = float(t.get("duration", 0.0))
            codec = t.get("codec", "???")
            # Parser only computes duration for PCM/ADPCM; for XMA/WMA it's 0
            # and we can't safely infer sample_count from byte size alone.
            if dur > 0.0:
                dur_str = f"{dur:.6f}"
                cnt_str = str(int(round(dur * rate)))
            else:
                dur_str = ""
                cnt_str = ""
            w.writerow([
                t.get("index", ""),
                dur_str,
                cnt_str,
                rate,
                int(t.get("chans", 0)),
                codec,
            ])
    finally:
        if out_stream is not sys.stdout:
            out_stream.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
