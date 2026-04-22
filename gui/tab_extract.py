"""Extract tab — Quick Mode working path.

Open an `.awb` file, see its waveforms listed with channels/rate/duration,
pick an output folder, click Extract All, get numbered WAVs.

Full Project mode (ACB-aware, cue-named) lands in Phase 2.
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.awb import AwbReader

from . import theme as T
from .formatting import format_duration
from .preview import AudioPreview
from .widgets import folder_row


class ExtractTab(tk.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        *,
        status_var: tk.StringVar,
        preview: AudioPreview,
    ) -> None:
        super().__init__(parent, bg=T.BG)
        self._status_var = status_var
        self._preview = preview
        # track row_id -> waveform list index for preview
        self._row_to_idx: dict[str, int] = {}

        self.awb_path_var = tk.StringVar()
        self.out_dir_var  = tk.StringVar()

        self._reader: AwbReader | None = None
        self._stop_event = threading.Event()
        self._running = False

        self._build()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Top: mode label
        mode_bar = tk.Frame(self, bg=T.BG)
        mode_bar.pack(fill="x", padx=20, pady=(10, 4))
        tk.Label(
            mode_bar, text="Quick Extract", font=T.FONT_BIG,
            bg=T.BG, fg=T.TEXT,
        ).pack(side="left")
        tk.Label(
            mode_bar, text="(AWB → numbered WAVs — for named output, use the Browse tab)",
            font=T.FONT_SM, bg=T.BG, fg=T.MUTED,
        ).pack(side="left", padx=(10, 0), pady=(6, 0))

        # Inputs
        folder_row(
            self, "AWB file (input):", self.awb_path_var,
            self._browse_awb,
            hint="Drag an .awb here or click Browse. PS4 and Switch RE4 both work.",
        )
        # Reuse folder_row for the output dir row
        folder_row(
            self, "Output folder:", self.out_dir_var,
            self._browse_out,
            hint="Where extracted WAV files will be saved.",
        )

        tk.Frame(self, bg=T.PANEL, height=1).pack(fill="x", padx=16, pady=(10, 8))

        # Waveform list
        list_outer = tk.Frame(self, bg=T.BG)
        list_outer.pack(fill="both", expand=True, padx=20, pady=(0, 4))

        tk.Label(
            list_outer, text="Waveforms", font=T.FONT, bg=T.BG, fg=T.MUTED,
        ).pack(anchor="w")

        cols = ("idx", "chans", "rate", "duration", "samples")
        self._tree = ttk.Treeview(list_outer, columns=cols, show="headings", height=10)
        for cid, label, w in [
            ("idx", "Index", 70),
            ("chans", "Ch", 40),
            ("rate", "Rate (Hz)", 90),
            ("duration", "Duration", 90),
            ("samples", "Samples", 100),
        ]:
            self._tree.heading(cid, text=label)
            self._tree.column(cid, width=w, anchor="w")

        style = ttk.Style(self)
        style.configure("Treeview",
                        background=T.PANEL, fieldbackground=T.PANEL, foreground=T.TEXT,
                        rowheight=22, borderwidth=0)
        style.configure("Treeview.Heading",
                        background=T.PANEL, foreground=T.MUTED, relief="flat",
                        font=T.FONT_SM)
        style.map("Treeview",
                  background=[("selected", T.ACCENT)],
                  foreground=[("selected", T.TEXT)])

        self._tree.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(list_outer, command=self._tree.yview, bg=T.PANEL,
                          troughcolor=T.PANEL, relief="flat")
        sb.pack(side="right", fill="y")
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.bind("<Double-Button-1>", lambda _e: self._preview_selected())

        # Progress
        prog_frame = tk.Frame(self, bg=T.BG)
        prog_frame.pack(fill="x", padx=20, pady=(4, 0))
        self._prog_label = tk.Label(prog_frame, text="", font=T.FONT_SM, bg=T.BG, fg=T.MUTED)
        self._prog_label.pack(side="right")

        self._progress = ttk.Progressbar(
            self, style="Custom.Horizontal.TProgressbar", mode="determinate",
        )
        self._progress.pack(fill="x", padx=20, pady=(0, 6))

        # Log
        log_frame = tk.Frame(self, bg=T.PANEL, bd=0)
        log_frame.pack(fill="both", expand=False, padx=20, pady=(0, 6))
        self._log = tk.Text(
            log_frame, font=T.FONT_SM, height=6,
            bg=T.PANEL, fg=T.TEXT, insertbackground=T.TEXT,
            relief="flat", bd=8, state="disabled", wrap="word", cursor="arrow",
        )
        self._log.pack(side="left", fill="both", expand=True)
        log_sb = tk.Scrollbar(log_frame, command=self._log.yview, bg=T.PANEL,
                              troughcolor=T.PANEL, relief="flat")
        log_sb.pack(side="right", fill="y")
        self._log.configure(yscrollcommand=log_sb.set)
        self._log.tag_configure("ok",    foreground=T.SUCCESS)
        self._log.tag_configure("error", foreground=T.ACCENT)
        self._log.tag_configure("info",  foreground=T.MUTED)

        # Buttons
        btn_frame = tk.Frame(self, bg=T.BG)
        btn_frame.pack(fill="x", padx=20, pady=(2, 10), anchor="w")

        self._start_btn = tk.Button(
            btn_frame, text="▶  Extract All", font=T.FONT,
            bg=T.ACCENT, fg=T.TEXT,
            activebackground=T.ACCENT_HOVER, activeforeground=T.TEXT,
            relief="flat", bd=0, padx=14, pady=8, cursor="hand2",
            command=self._start, state="disabled",
        )
        self._start_btn.pack(side="left", padx=(0, 6))

        self._stop_btn = tk.Button(
            btn_frame, text="■  Stop", font=T.FONT,
            bg=T.PANEL, fg=T.MUTED,
            activebackground="#2a2a4e", activeforeground=T.TEXT,
            relief="flat", bd=0, padx=14, pady=8, cursor="hand2",
            command=self._stop, state="disabled",
        )
        self._stop_btn.pack(side="left", padx=(0, 6))

        tk.Button(
            btn_frame, text="♪  Preview", font=T.FONT,
            bg=T.PANEL, fg=T.TEXT,
            activebackground=T.ACCENT, activeforeground=T.TEXT,
            relief="flat", bd=0, padx=14, pady=8, cursor="hand2",
            command=self._preview_selected,
        ).pack(side="left", padx=(12, 6))

        tk.Button(
            btn_frame, text="■  Stop preview", font=T.FONT,
            bg=T.PANEL, fg=T.MUTED,
            activebackground="#2a2a4e", activeforeground=T.TEXT,
            relief="flat", bd=0, padx=14, pady=8, cursor="hand2",
            command=self._preview.stop,
        ).pack(side="left", padx=(0, 6))

    # ── callbacks ─────────────────────────────────────────────────────────────

    def _preview_selected(self) -> None:
        if self._reader is None:
            return
        sel = self._tree.selection()
        if not sel:
            self._set_status("Select a waveform row to preview.")
            return
        # Tree rows are inserted in waveform order, so the tree index == AWB index.
        idx = self._tree.index(sel[0])
        try:
            blob = self._reader._awb.get_file_at(idx)
        except Exception as e:  # noqa: BLE001
            self._log_line(f"Preview failed: {e}", "error")
            return
        self._set_status(f"Preview: track {idx:04d}")
        self._preview.play_hca_bytes_async(
            blob,
            on_error=lambda msg: self.after(0, lambda: self._log_line(f"Preview failed: {msg}", "error")),
        )

    def _browse_awb(self) -> None:
        path = filedialog.askopenfilename(
            title="Open AWB",
            filetypes=[("AWB files", "*.awb"), ("All files", "*.*")],
        )
        if not path:
            return
        self.awb_path_var.set(path)
        # Default output dir beside the AWB
        if not self.out_dir_var.get():
            self.out_dir_var.set(str(Path(path).with_suffix("").parent / (Path(path).stem + "_wav")))
        self._load_awb(path)

    def _browse_out(self) -> None:
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.out_dir_var.set(path)

    def _load_awb(self, path: str) -> None:
        self._tree.delete(*self._tree.get_children())
        self._reader = None
        self._start_btn.config(state="disabled")
        try:
            reader = AwbReader(path)
            wfs = reader.waveforms()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Open AWB failed", f"{e}")
            self._set_status(f"Failed to open {os.path.basename(path)}")
            return

        self._reader = reader
        for w in wfs:
            self._tree.insert(
                "", "end",
                values=(
                    f"{w.index:04d}",
                    w.channels,
                    w.sample_rate,
                    format_duration(w.duration_s),
                    f"{w.sample_count:,}",
                ),
            )
        self._set_status(f"{os.path.basename(path)} — {reader.numfiles} waveforms")
        self._log_line(f"Opened {path} ({reader.numfiles} waveforms)", "info")
        self._start_btn.config(state="normal")

    def _start(self) -> None:
        if self._running or self._reader is None:
            return
        out_dir = self.out_dir_var.get().strip()
        if not out_dir:
            messagebox.showwarning("Missing output folder", "Choose an output folder first.")
            return

        self._stop_event.clear()
        self._set_running(True)
        self._progress.config(value=0, maximum=self._reader.numfiles)
        self._prog_label.config(text=f"0 / {self._reader.numfiles}")
        self._log_line(f"Extracting to {out_dir}", "info")

        t = threading.Thread(target=self._work, args=(out_dir,), daemon=True)
        t.start()

    def _stop(self) -> None:
        self._stop_event.set()
        self._set_status("Stopping…")

    def _work(self, out_dir: str) -> None:
        reader = self._reader
        assert reader is not None
        try:
            written = reader.extract_all(
                out_dir,
                progress_cb=self._progress_from_worker,
                log_cb=self._log_from_worker,
                stop_event=self._stop_event,
            )
            done_msg = f"Done — {len(written)} files written to {out_dir}"
            self.after(0, lambda: self._log_line(done_msg, "ok"))
            self.after(0, lambda: self._set_status(done_msg))
        except Exception as e:  # noqa: BLE001
            err = str(e)
            self.after(0, lambda: self._log_line(f"Extraction error: {err}", "error"))
            self.after(0, lambda: self._set_status("Extraction failed."))
        finally:
            self.after(0, lambda: self._set_running(False))

    # ── worker -> GUI bridges (always via self.after) ─────────────────────────

    def _progress_from_worker(self, done: int, total: int) -> None:
        self.after(0, lambda: self._update_progress(done, total))

    def _log_from_worker(self, msg: str, tag: str) -> None:
        self.after(0, lambda: self._log_line(msg, tag))

    def _update_progress(self, done: int, total: int) -> None:
        self._progress.config(value=done, maximum=total)
        self._prog_label.config(text=f"{done} / {total}")

    def _log_line(self, msg: str, tag: str = "info") -> None:
        self._log.config(state="normal")
        self._log.insert("end", msg + "\n", tag)
        self._log.see("end")
        self._log.config(state="disabled")

    def _set_running(self, running: bool) -> None:
        self._running = running
        self._start_btn.config(state="disabled" if running else ("normal" if self._reader else "disabled"))
        self._stop_btn.config(state="normal" if running else "disabled")

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)
