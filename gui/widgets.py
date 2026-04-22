"""Reusable widget helpers. Port of XWB Tool patterns."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import theme as T


def folder_row(
    parent: tk.Widget,
    label: str,
    var: tk.StringVar,
    browse_cb,
    *,
    hint: str = "",
) -> tk.Frame:
    """Label + entry + browse button + hint line. Mirrors XWB Tool's _folder_row."""
    outer = tk.Frame(parent, bg=T.BG)
    outer.pack(fill="x", padx=20, pady=(6, 2))

    tk.Label(outer, text=label, font=T.FONT, bg=T.BG, fg=T.TEXT).pack(anchor="w")

    row = tk.Frame(outer, bg=T.BG)
    row.pack(fill="x", pady=(2, 0))

    entry = tk.Entry(
        row, textvariable=var, font=T.FONT,
        bg=T.PANEL, fg=T.TEXT, insertbackground=T.TEXT,
        relief="flat", bd=6,
    )
    entry.pack(side="left", fill="x", expand=True)

    tk.Button(
        row, text="Browse…", font=T.FONT, bg=T.PANEL, fg=T.TEXT,
        activebackground=T.ACCENT, activeforeground=T.TEXT,
        relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
        command=browse_cb,
    ).pack(side="left", padx=(6, 0))

    if hint:
        tk.Label(outer, text=hint, font=T.FONT_SM, bg=T.BG, fg=T.MUTED).pack(anchor="w", pady=(2, 0))

    return outer


def make_progressbar_style(root: tk.Tk) -> None:
    """Install the Custom.Horizontal.TProgressbar style used by the GUI."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        "Custom.Horizontal.TProgressbar",
        troughcolor=T.PANEL, background=T.ACCENT,
        bordercolor=T.PANEL, lightcolor=T.ACCENT, darkcolor=T.ACCENT,
    )


def placeholder_frame(parent: tk.Widget, *, title: str, subtitle: str) -> tk.Frame:
    """A simple centered 'Coming in Phase N' frame."""
    f = tk.Frame(parent, bg=T.BG)
    inner = tk.Frame(f, bg=T.BG)
    inner.place(relx=0.5, rely=0.45, anchor="center")
    tk.Label(inner, text=title, font=T.FONT_BIG, bg=T.BG, fg=T.TEXT).pack()
    tk.Label(inner, text=subtitle, font=T.FONT, bg=T.BG, fg=T.MUTED).pack(pady=(8, 0))
    return f
