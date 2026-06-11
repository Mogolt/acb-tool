"""Convert tab — standalone WAV ↔ HCA, batch-capable, mode-independent."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.hca import Quality, decode_hca_to_wav, encode_wav_to_hca

from . import theme as T
from .preview import AudioPreview
from .widgets import folder_row


DIRECTION_AUTO     = "Auto-detect by extension"
DIRECTION_WAV2HCA  = "WAV → HCA (encode)"
DIRECTION_HCA2WAV  = "HCA → WAV (decode)"

QUALITY_CHOICES = [
    ("Highest (default — required for PSNR ≥ 40 dB)", Quality.HIGHEST),
    ("High",    Quality.HIGH),
    ("Middle",  Quality.MIDDLE),
    ("Low",     Quality.LOW),
    ("Lowest",  Quality.LOWEST),
]


class ConvertTab(tk.Frame):
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

        self.out_dir_var   = tk.StringVar()
        self.direction_var = tk.StringVar(value=DIRECTION_AUTO)
        self.quality_var   = tk.StringVar(value=QUALITY_CHOICES[0][0])  # Highest

        self._files: list[Path] = []
        self._stop_event = threading.Event()
        self._running = False

        self._build()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        mode_bar = tk.Frame(self, bg=T.BG)
        mode_bar.pack(fill="x", padx=20, pady=(10, 4))
        tk.Label(
            mode_bar, text="Convert", font=T.FONT_BIG, bg=T.BG, fg=T.TEXT,
        ).pack(side="left")
        tk.Label(
            mode_bar, text="(standalone WAV ↔ HCA, batch — no ACB/AWB needed)",
            font=T.FONT_SM, bg=T.BG, fg=T.MUTED,
        ).pack(side="left", padx=(10, 0), pady=(6, 0))

        folder_row(
            self, "Output folder:", self.out_dir_var, self._browse_out,
            hint="Converted files land here with the opposite extension.",
        )

        # Options row
        opts = tk.Frame(self, bg=T.BG)
        opts.pack(fill="x", padx=20, pady=(6, 4))

        tk.Label(opts, text="Direction:", font=T.FONT, bg=T.BG, fg=T.TEXT).pack(side="left")
        ttk.Combobox(
            opts, textvariable=self.direction_var,
            values=[DIRECTION_AUTO, DIRECTION_WAV2HCA, DIRECTION_HCA2WAV],
            state="readonly", width=30, font=T.FONT,
        ).pack(side="left", padx=(8, 20))

        tk.Label(opts, text="Quality (WAV→HCA):", font=T.FONT, bg=T.BG, fg=T.TEXT).pack(side="left")
        ttk.Combobox(
            opts, textvariable=self.quality_var,
            values=[name for name, _ in QUALITY_CHOICES],
            state="readonly", width=16, font=T.FONT,
        ).pack(side="left", padx=(8, 0))

        tk.Frame(self, bg=T.PANEL, height=1).pack(fill="x", padx=16, pady=(8, 8))

        # File list
        list_outer = tk.Frame(self, bg=T.BG)
        list_outer.pack(fill="both", expand=True, padx=20, pady=(0, 4))

        tk.Label(
            list_outer, text="Files to convert", font=T.FONT, bg=T.BG, fg=T.MUTED,
        ).pack(anchor="w")

        inner = tk.Frame(list_outer, bg=T.BG)
        inner.pack(fill="both", expand=True)

        self._listbox = tk.Listbox(
            inner, font=T.FONT_SM,
            bg=T.PANEL, fg=T.TEXT, selectbackground=T.ACCENT, selectforeground=T.TEXT,
            relief="flat", bd=6, highlightthickness=0, activestyle="none",
            selectmode="extended",
        )
        self._listbox.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(inner, command=self._listbox.yview, bg=T.PANEL,
                          troughcolor=T.PANEL, relief="flat")
        sb.pack(side="right", fill="y")
        self._listbox.configure(yscrollcommand=sb.set)
        self._listbox.bind("<Double-Button-1>", lambda _e: self._preview_selected())

        # List buttons
        lbtns = tk.Frame(self, bg=T.BG)
        lbtns.pack(fill="x", padx=20, pady=(4, 4))
        for text, cmd in [
            ("+ Add files…",   self._add_files),
            ("– Remove selected", self._remove_selected),
            ("⌫ Clear",         self._clear_list),
        ]:
            tk.Button(
                lbtns, text=text, font=T.FONT, bg=T.PANEL, fg=T.TEXT,
                activebackground=T.ACCENT, activeforeground=T.TEXT,
                relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
                command=cmd,
            ).pack(side="left", padx=(0, 6))

        tk.Button(
            lbtns, text="♪ Preview", font=T.FONT, bg=T.PANEL, fg=T.TEXT,
            activebackground=T.ACCENT, activeforeground=T.TEXT,
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=self._preview_selected,
        ).pack(side="left", padx=(12, 6))

        tk.Button(
            lbtns, text="■ Stop preview", font=T.FONT, bg=T.PANEL, fg=T.MUTED,
            activebackground="#2a2a4e", activeforeground=T.TEXT,
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=self._preview.stop,
        ).pack(side="left", padx=(0, 6))

        # Progress
        prog_frame = tk.Frame(self, bg=T.BG)
        prog_frame.pack(fill="x", padx=20, pady=(6, 0))
        self._prog_label = tk.Label(prog_frame, text="", font=T.FONT_SM, bg=T.BG, fg=T.MUTED)
        self._prog_label.pack(side="right")

        self._progress = ttk.Progressbar(
            self, style="Custom.Horizontal.TProgressbar", mode="determinate",
        )
        self._progress.pack(fill="x", padx=20, pady=(0, 6))

        # Log
        log_frame = tk.Frame(self, bg=T.PANEL, bd=0)
        log_frame.pack(fill="x", expand=False, padx=20, pady=(0, 6))
        self._log = tk.Text(
            log_frame, font=T.FONT_SM, height=5,
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
            btn_frame, text="▶  Convert", font=T.FONT,
            bg=T.ACCENT, fg=T.TEXT,
            activebackground=T.ACCENT_HOVER, activeforeground=T.TEXT,
            relief="flat", bd=0, padx=14, pady=8, cursor="hand2",
            command=self._start,
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

    # ── callbacks ─────────────────────────────────────────────────────────────

    def _browse_out(self) -> None:
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.out_dir_var.set(path)

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Add WAV or HCA files",
            filetypes=[("Audio", "*.wav *.hca"), ("WAV", "*.wav"), ("HCA", "*.hca"), ("All", "*.*")],
        )
        for p in paths:
            pth = Path(p)
            if pth not in self._files:
                self._files.append(pth)
                self._listbox.insert("end", str(pth))

    def _remove_selected(self) -> None:
        for idx in reversed(self._listbox.curselection()):
            del self._files[idx]
            self._listbox.delete(idx)

    def _clear_list(self) -> None:
        self._files.clear()
        self._listbox.delete(0, "end")

    def _preview_selected(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            self._set_status("Select a file in the list to preview.")
            return
        path = self._files[sel[0]]
        self._set_status(f"Preview: {path.name}")
        self._preview.play_path_async(
            path,
            on_error=lambda msg: self.after(0, lambda: self._log_line(f"Preview failed: {msg}", "error")),
        )

    def _start(self) -> None:
        if self._running:
            return
        if not self._files:
            messagebox.showwarning("No files", "Add WAV or HCA files to the list first.")
            return
        out_dir = self.out_dir_var.get().strip()
        if not out_dir:
            messagebox.showwarning("Missing output folder", "Choose an output folder first.")
            return

        quality = next(q for n, q in QUALITY_CHOICES if n == self.quality_var.get())
        direction = self.direction_var.get()

        self._stop_event.clear()
        self._set_running(True)
        self._progress.config(value=0, maximum=len(self._files))
        self._prog_label.config(text=f"0 / {len(self._files)}")
        self._log_line(f"Converting {len(self._files)} file(s) → {out_dir}", "info")

        threading.Thread(
            target=self._work,
            args=(list(self._files), Path(out_dir), direction, quality),
            daemon=True,
        ).start()

    def _stop(self) -> None:
        self._stop_event.set()
        self._set_status("Stopping…")

    def _work(self, files: list[Path], out_dir: Path, direction: str, quality: Quality) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        done = 0
        succeeded = 0
        for i, src in enumerate(files):
            if self._stop_event.is_set():
                break

            dir_for_file = self._resolve_direction(src, direction)
            if dir_for_file is None:
                self.after(0, lambda p=src: self._log_line(f"  skip (unrecognized): {p.name}", "error"))
                done = i + 1
                self.after(0, lambda d=done, t=len(files): self._update_progress(d, t))
                continue

            is_encode = dir_for_file == DIRECTION_WAV2HCA
            out_path = out_dir / (src.stem + (".hca" if is_encode else ".wav"))

            try:
                if is_encode:
                    encode_wav_to_hca(src, out_path, quality=quality)
                else:
                    decode_hca_to_wav(src, out_path)
                self.after(0, lambda p=out_path: self._log_line(f"  ok   {p.name}", "ok"))
                succeeded += 1
            except Exception as e:  # noqa: BLE001
                err = str(e)
                self.after(0, lambda p=src, er=err: self._log_line(f"  fail {p.name}: {er}", "error"))

            done = i + 1
            self.after(0, lambda d=done, t=len(files): self._update_progress(d, t))

        msg = f"Done — {succeeded}/{len(files)} files converted."
        self.after(0, lambda: self._log_line(msg, "ok" if succeeded == len(files) else "info"))
        self.after(0, lambda: self._set_status(msg))
        self.after(0, lambda: self._set_running(False))

    @staticmethod
    def _resolve_direction(src: Path, direction: str) -> str | None:
        if direction == DIRECTION_WAV2HCA:
            return DIRECTION_WAV2HCA
        if direction == DIRECTION_HCA2WAV:
            return DIRECTION_HCA2WAV
        ext = src.suffix.lower()
        if ext == ".wav":
            return DIRECTION_WAV2HCA
        if ext == ".hca":
            return DIRECTION_HCA2WAV
        return None

    # ── worker -> GUI bridges ─────────────────────────────────────────────────

    def _update_progress(self, done: int, total: int) -> None:
        self._progress.config(value=done, maximum=max(total, 1))
        self._prog_label.config(text=f"{done} / {total}")

    def _log_line(self, msg: str, tag: str = "info") -> None:
        self._log.config(state="normal")
        self._log.insert("end", msg + "\n", tag)
        self._log.see("end")
        self._log.config(state="disabled")

    def _set_running(self, running: bool) -> None:
        self._running = running
        self._start_btn.config(state="disabled" if running else "normal")
        self._stop_btn.config(state="normal" if running else "disabled")

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)
