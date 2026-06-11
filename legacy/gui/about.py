"""About dialog — modal, dark-themed, text-only.

Version string comes from ``core/__version__.py`` so the About dialog, the
future Inno Setup installer, and any other consumer all read the same value.
"""

from __future__ import annotations

import tkinter as tk

from core.version import __app_name__, __author__, __repo_url__, __version__

from . import theme as T


_TAGLINE = "Extract and inject ACB/AWB audio banks from Resident Evil 4 on PS4 and Switch."

_USAGE_LINES: list[tuple[str, str]] = [
    ("Browse",  "Open an ACB to explore cues by name; extract the whole bank as named WAVs."),
    ("Extract", "Open an AWB directly for quick numbered extraction (no ACB required)."),
    ("Inject",  "Replace waveforms, rebuild AWB, patch ACB. Preview before saving."),
    ("Convert", "Standalone WAV ↔ HCA, batch-capable."),
]

_CREDITS: list[tuple[str, str]] = [
    ("PyCriCodecsEx",  "mos9527 — CRIWARE ACB/AWB/HCA read + write"),
    ("PyCriCodecs",    "Youjose — upstream of PyCriCodecsEx"),
    ("vgmstream",      "canonical HCA / ADX reference decoder"),
    ("VGAudio",        "Thealexbarney — HCA encoder reference"),
]


class AboutDialog(tk.Toplevel):
    """Modal About window. Esc or OK closes it."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title(f"About {__app_name__}")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Top accent strip — matches the main window's title bar.
        tk.Frame(self, bg=T.ACCENT, height=4).pack(fill="x")

        body = tk.Frame(self, bg=T.BG)
        body.pack(padx=24, pady=18, fill="both")

        # Title line
        title_row = tk.Frame(body, bg=T.BG)
        title_row.pack(fill="x")
        tk.Label(
            title_row, text=__app_name__,
            font=T.FONT_BIG, bg=T.BG, fg=T.TEXT,
        ).pack(side="left")
        tk.Label(
            title_row, text=f"v{__version__}",
            font=T.FONT_SM, bg=T.BG, fg=T.MUTED,
        ).pack(side="left", padx=(10, 0), pady=(6, 0))

        # Tagline
        tk.Label(
            body, text=_TAGLINE,
            font=T.FONT_SM, bg=T.BG, fg=T.MUTED,
            wraplength=540, justify="left",
        ).pack(anchor="w", pady=(6, 14))

        # Usage section
        tk.Label(
            body, text="Tabs", font=T.FONT, bg=T.BG, fg=T.TEXT,
        ).pack(anchor="w")
        for name, desc in _USAGE_LINES:
            row = tk.Frame(body, bg=T.BG)
            row.pack(fill="x", pady=(2, 0))
            tk.Label(
                row, text=f"  {name:<9s}",
                font=T.FONT_SM, bg=T.BG, fg=T.ACCENT,
            ).pack(side="left")
            tk.Label(
                row, text=desc,
                font=T.FONT_SM, bg=T.BG, fg=T.TEXT,
                wraplength=460, justify="left",
            ).pack(side="left")

        # Credits section
        tk.Frame(body, bg=T.PANEL, height=1).pack(fill="x", pady=(14, 10))
        tk.Label(
            body, text="Credits", font=T.FONT, bg=T.BG, fg=T.TEXT,
        ).pack(anchor="w")
        for name, desc in _CREDITS:
            row = tk.Frame(body, bg=T.BG)
            row.pack(fill="x", pady=(2, 0))
            tk.Label(
                row, text=f"  {name}",
                font=T.FONT_SM, bg=T.BG, fg=T.SUCCESS,
            ).pack(side="left")
            tk.Label(
                row, text=f"  — {desc}",
                font=T.FONT_SM, bg=T.BG, fg=T.MUTED,
                wraplength=420, justify="left",
            ).pack(side="left")

        # Footer: author + repo
        tk.Frame(body, bg=T.PANEL, height=1).pack(fill="x", pady=(14, 10))
        footer = tk.Frame(body, bg=T.BG)
        footer.pack(fill="x")
        tk.Label(
            footer, text=f"Made by {__author__}",
            font=T.FONT_SM, bg=T.BG, fg=T.TEXT,
        ).pack(side="left")
        tk.Label(
            footer,
            text=__repo_url__ if __repo_url__ else "(repo url tbd)",
            font=T.FONT_SM, bg=T.BG, fg=T.MUTED,
        ).pack(side="right")

        # OK button
        ok = tk.Button(
            body, text="OK", font=T.FONT,
            bg=T.ACCENT, fg=T.TEXT,
            activebackground=T.ACCENT_HOVER, activeforeground=T.TEXT,
            relief="flat", bd=0, padx=22, pady=6, cursor="hand2",
            command=self.destroy,
        )
        ok.pack(anchor="e", pady=(16, 0))
        ok.focus_set()

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self.destroy())

        self._center_on_parent(parent)

    def _center_on_parent(self, parent: tk.Misc) -> None:
        parent.update_idletasks()
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        self.geometry(f"+{x}+{y}")
