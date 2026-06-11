"""Display formatters shared across the GUI.

Centralized so the "< 60 s shows seconds, >= 60 s shows m:ss" rule is defined
once. CSV / file-export paths should NOT use these helpers — they want raw
numbers so downstream tools stay unambiguous.
"""

from __future__ import annotations


def format_duration(seconds: float) -> str:
    """Format a duration for GUI display.

    * < 60 s:   ``"3.04 s"`` — two decimals preserved for short SFX.
    * >= 60 s:  ``"m:ss"`` / ``"mm:ss"`` — seconds zero-padded to 2 digits,
                minutes NOT padded. Rounds to the nearest whole second.

    Negative or non-finite durations display as ``"0.00 s"``.
    """
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return "0.00 s"
    if not (s == s) or s == float("inf") or s == float("-inf"):  # NaN / inf
        return "0.00 s"
    if s < 60.0:
        return f"{max(s, 0.0):.2f} s"
    total = int(round(s))
    mins, secs = divmod(total, 60)
    return f"{mins}:{secs:02d}"
