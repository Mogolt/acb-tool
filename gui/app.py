"""App(tk.Tk) shell — tab bar, status bar, theme setup."""

from __future__ import annotations

import tkinter as tk

from . import theme as T
from core.version import __app_name__, __version__

from .about import AboutDialog
from .preview import AudioPreview
from .tab_browse import BrowseTab
from .tab_convert import ConvertTab
from .tab_extract import ExtractTab
from .tab_inject import InjectTab
from .widgets import make_progressbar_style


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ACB Tool")
        self.configure(bg=T.BG)
        # NOTE: no geometry/minsize here. They get set after _build() once we
        # know every tab's natural requested size — see _lock_window_size.

        self._status_var = tk.StringVar(value="Ready.")
        self._current_tab = "browse"
        # One preview instance across all tabs — switching tabs or previewing
        # a different clip stops the current one automatically.
        self._preview = AudioPreview()

        make_progressbar_style(self)
        self._build()
        self._lock_window_size()

        # Stop playback when the window closes so we don't leak winsound state.
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        # Top accent bar
        tk.Frame(self, bg=T.ACCENT, height=4).pack(fill="x")

        # Header
        header = tk.Frame(self, bg=T.BG)
        header.pack(fill="x", padx=20, pady=(14, 4))
        tk.Label(header, text=__app_name__, font=T.FONT_BIG,
                 bg=T.BG, fg=T.TEXT).pack(side="left")
        tk.Label(header, text="for RE4 PS4 & Switch (CRIWARE ADX2)",
                 font=T.FONT_SM, bg=T.BG, fg=T.MUTED).pack(side="left", padx=(10, 0), pady=(4, 0))
        tk.Button(
            header, text="?", font=T.FONT_BIG,
            bg=T.PANEL, fg=T.MUTED,
            activebackground=T.ACCENT, activeforeground=T.TEXT,
            relief="flat", bd=0, padx=10, pady=2, cursor="hand2",
            command=self._show_about,
        ).pack(side="right")

        # Tab bar
        tab_bar = tk.Frame(self, bg=T.BG)
        tab_bar.pack(fill="x")

        self._tab_btns: dict[str, tk.Label] = {}
        for key, label in [
            ("browse",  "   Browse   "),
            ("extract", "   Extract   "),
            ("inject",  "   Inject   "),
            ("convert", "   Convert   "),
        ]:
            btn = tk.Label(tab_bar, text=label, font=T.FONT_BIG,
                           cursor="hand2", pady=10, padx=8)
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda e, k=key: self._switch_tab(k))
            self._tab_btns[key] = btn

        # Thin accent line under the tab bar
        tk.Frame(self, bg=T.ACCENT, height=2).pack(fill="x")
        tk.Frame(self, bg=T.PANEL, height=1).pack(fill="x", padx=16, pady=(0, 8))

        # Status bar at bottom
        status_bar = tk.Frame(self, bg=T.PANEL)
        status_bar.pack(fill="x", side="bottom")
        tk.Label(status_bar, textvariable=self._status_var, font=T.FONT_SM,
                 bg=T.PANEL, fg=T.MUTED, anchor="w").pack(side="left", padx=10, pady=4)

        # Content frames
        self._tabs: dict[str, tk.Frame] = {
            "browse":  BrowseTab(self, status_var=self._status_var, preview=self._preview),
            "extract": ExtractTab(self, status_var=self._status_var, preview=self._preview),
            "inject":  InjectTab(self, status_var=self._status_var, preview=self._preview),
            "convert": ConvertTab(self, status_var=self._status_var, preview=self._preview),
        }

        self._switch_tab("browse")

    def _switch_tab(self, tab: str) -> None:
        # Stop any in-flight preview so audio doesn't keep playing across tabs.
        if hasattr(self, "_preview"):
            self._preview.stop()
        self._current_tab = tab
        for key, frame in self._tabs.items():
            frame.pack_forget()
        self._tabs[tab].pack(fill="both", expand=True)
        for key, btn in self._tab_btns.items():
            if key == tab:
                btn.config(bg=T.BG, fg=T.TAB_FG_ACT)
            else:
                btn.config(bg=T.TAB_INACT, fg=T.TAB_FG_INACT)

    def _on_close(self) -> None:
        self._preview.stop()
        self.destroy()

    def _show_about(self) -> None:
        AboutDialog(self)

    def _lock_window_size(self) -> None:
        """Measure every tab's natural requested size, pick the worst case,
        and lock minsize to it so no tab can ever clip its controls. Launch
        geometry is the worst-case plus a small slack, centered on screen.

        This mirrors XWB Tool's pattern (xwb_tool.py:712) but walks all tabs
        instead of relying on whichever one happens to be visible at init.
        """
        self.update_idletasks()

        original_tab = self._current_tab
        max_w = 0
        max_h = 0
        for tab_name in self._tabs:
            self._switch_tab(tab_name)
            self.update_idletasks()
            w = self.winfo_reqwidth()
            h = self.winfo_reqheight()
            if w > max_w:
                max_w = w
            if h > max_h:
                max_h = h
        self._switch_tab(original_tab)
        self.update_idletasks()

        # A tiny slack accounts for tkinter's occasional 1-px rounding between
        # reqheight and actual geometry.
        min_w = max_w + 4
        min_h = max_h + 4
        self.minsize(min_w, min_h)

        # Launch a touch larger than minsize for breathing room, but never
        # bigger than the screen (leaves space for taskbar, macOS dock, etc.).
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        init_w = min(min_w + 40, sw - 40)
        init_h = min(min_h + 40, sh - 80)
        x = max(0, (sw - init_w) // 2)
        y = max(0, (sh - init_h) // 2)
        self.geometry(f"{init_w}x{init_h}+{x}+{y}")


def main() -> None:
    App().mainloop()
