"""Browse tab — Full Project Mode.

Open an `.acb`, auto-pair its companion `.awb`, browse cues by name, see
per-waveform metadata (channels, rate, duration, loop), and extract the
whole bank as named WAVs (cue name → filename).
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.models import Cue, Waveform
from core.project import Project, ProjectLoadError

from . import theme as T
from .formatting import format_duration
from .preview import AudioPreview
from .widgets import folder_row


class BrowseTab(tk.Frame):
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

        self.acb_path_var = tk.StringVar()
        self.out_dir_var  = tk.StringVar()

        self._project: Project | None = None
        self._stop_event = threading.Event()
        self._running = False
        # row-id -> waveform table index, for the waveform list on the right
        self._wf_row_to_table_idx: dict[str, int] = {}

        self._build()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        mode_bar = tk.Frame(self, bg=T.BG)
        mode_bar.pack(fill="x", padx=20, pady=(10, 4))
        tk.Label(
            mode_bar, text="Full Project", font=T.FONT_BIG,
            bg=T.BG, fg=T.TEXT,
        ).pack(side="left")
        tk.Label(
            mode_bar, text="(ACB + AWB → named WAVs using cue names)",
            font=T.FONT_SM, bg=T.BG, fg=T.MUTED,
        ).pack(side="left", padx=(10, 0), pady=(6, 0))

        folder_row(
            self, "ACB file (input):", self.acb_path_var,
            self._browse_acb,
            hint="Open an .acb; its companion .awb must sit in the same folder.",
        )
        folder_row(
            self, "Output folder:", self.out_dir_var,
            self._browse_out,
            hint="Files are named after cues, e.g. LEON_GRUNT_HIT_01.wav",
        )

        tk.Frame(self, bg=T.PANEL, height=1).pack(fill="x", padx=16, pady=(10, 8))

        # Paned split: cue tree (left) + waveform list (right)
        split = tk.PanedWindow(
            self, orient="horizontal", bg=T.PANEL,
            sashwidth=6, sashrelief="flat", bd=0, handlesize=0,
        )
        split.pack(fill="both", expand=True, padx=20, pady=(0, 4))

        # Left: cue tree
        left = tk.Frame(split, bg=T.BG)
        split.add(left, minsize=300, stretch="always")

        tk.Label(left, text="Cues", font=T.FONT, bg=T.BG, fg=T.MUTED).pack(anchor="w")

        cue_cols = ("cueid", "length", "wfs")
        self._cue_tree = ttk.Treeview(left, columns=cue_cols, show="tree headings", height=14)
        self._cue_tree.heading("#0", text="Name")
        self._cue_tree.heading("cueid",  text="Cue ID")
        self._cue_tree.heading("length", text="Length")
        self._cue_tree.heading("wfs",    text="Waves")
        self._cue_tree.column("#0",     width=250, anchor="w")
        self._cue_tree.column("cueid",  width=70,  anchor="w")
        self._cue_tree.column("length", width=80,  anchor="w")
        self._cue_tree.column("wfs",    width=60,  anchor="w")
        self._cue_tree.pack(side="left", fill="both", expand=True)
        cue_sb = tk.Scrollbar(left, command=self._cue_tree.yview, bg=T.PANEL,
                              troughcolor=T.PANEL, relief="flat")
        cue_sb.pack(side="right", fill="y")
        self._cue_tree.configure(yscrollcommand=cue_sb.set)
        self._cue_tree.bind("<<TreeviewSelect>>", self._on_cue_select)

        # Right: waveform list
        right = tk.Frame(split, bg=T.BG)
        split.add(right, minsize=300, stretch="always")

        tk.Label(right, text="Waveforms", font=T.FONT, bg=T.BG, fg=T.MUTED).pack(anchor="w")

        wf_cols = ("awbid", "codec", "ch", "rate", "duration", "samples", "loop")
        self._wf_tree = ttk.Treeview(right, columns=wf_cols, show="headings", height=14)
        for cid, label, w in [
            ("awbid",   "AWB Id",    70),
            ("codec",   "Codec",     60),
            ("ch",      "Ch",        40),
            ("rate",    "Rate (Hz)", 80),
            ("duration","Duration",  80),
            ("samples", "Samples",   90),
            ("loop",    "Loop",      50),
        ]:
            self._wf_tree.heading(cid, text=label)
            self._wf_tree.column(cid, width=w, anchor="w")
        self._wf_tree.pack(side="left", fill="both", expand=True)
        wf_sb = tk.Scrollbar(right, command=self._wf_tree.yview, bg=T.PANEL,
                             troughcolor=T.PANEL, relief="flat")
        wf_sb.pack(side="right", fill="y")
        self._wf_tree.configure(yscrollcommand=wf_sb.set)
        self._wf_tree.bind("<Double-Button-1>", lambda _e: self._preview_selected_waveform())

        self._install_tree_style()

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
            btn_frame, text="▶  Extract All (named)", font=T.FONT,
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

        self._preview_btn = tk.Button(
            btn_frame, text="♪  Preview", font=T.FONT,
            bg=T.PANEL, fg=T.TEXT,
            activebackground=T.ACCENT, activeforeground=T.TEXT,
            relief="flat", bd=0, padx=14, pady=8, cursor="hand2",
            command=self._preview_selected_waveform,
        )
        self._preview_btn.pack(side="left", padx=(12, 6))

        self._preview_stop_btn = tk.Button(
            btn_frame, text="■  Stop preview", font=T.FONT,
            bg=T.PANEL, fg=T.MUTED,
            activebackground="#2a2a4e", activeforeground=T.TEXT,
            relief="flat", bd=0, padx=14, pady=8, cursor="hand2",
            command=self._preview.stop,
        )
        self._preview_stop_btn.pack(side="left", padx=(0, 6))

    def _install_tree_style(self) -> None:
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

    # ── callbacks ─────────────────────────────────────────────────────────────

    def _browse_acb(self) -> None:
        path = filedialog.askopenfilename(
            title="Open ACB",
            filetypes=[("ACB files", "*.acb"), ("All files", "*.*")],
        )
        if not path:
            return
        self.acb_path_var.set(path)
        if not self.out_dir_var.get():
            self.out_dir_var.set(str(Path(path).parent / (Path(path).stem + "_wav")))
        self._load_project(path)

    def _browse_out(self) -> None:
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.out_dir_var.set(path)

    def _load_project(self, path: str) -> None:
        self._cue_tree.delete(*self._cue_tree.get_children())
        self._wf_tree.delete(*self._wf_tree.get_children())
        self._wf_row_to_table_idx.clear()
        self._project = None
        self._start_btn.config(state="disabled")

        try:
            project = Project.open(path)
        except ProjectLoadError as e:
            messagebox.showerror("Open ACB failed", str(e))
            self._set_status(f"Failed to open {os.path.basename(path)}")
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Open ACB failed", f"{e}")
            self._set_status(f"Failed to open {os.path.basename(path)}")
            return

        self._project = project
        cues = project.cues()
        wfs = project.waveforms()

        # Populate cue tree
        for c in cues:
            self._cue_tree.insert(
                "", "end",
                text=c.name,
                values=(
                    c.cue_id,
                    format_duration(c.length_s),
                    len(c.waveform_indices),
                ),
            )

        # Populate waveform list
        for table_idx, w in enumerate(wfs):
            row_id = self._wf_tree.insert(
                "", "end",
                values=(
                    w.index,
                    w.codec,
                    w.channels,
                    w.sample_rate,
                    format_duration(w.duration_s),
                    f"{w.sample_count:,}",
                    "yes" if w.loop_flag else "",
                ),
            )
            self._wf_row_to_table_idx[row_id] = table_idx

        summary = (
            f"{project.acb.path.name}  +  {project.awb.path.name}  "
            f"— {len(cues)} cues, {len(wfs)} waveforms"
        )
        self._set_status(summary)
        self._log_line(f"Opened {project.acb.path}", "info")
        self._log_line(f"Paired  {project.awb.path}", "info")
        self._start_btn.config(state="normal")

    def _preview_selected_waveform(self) -> None:
        if self._project is None:
            return
        sel = self._wf_tree.selection()
        if not sel:
            self._set_status("Select a waveform row to preview.")
            return
        table_idx = self._wf_row_to_table_idx.get(sel[0])
        if table_idx is None:
            return
        wf = self._project.waveforms()[table_idx]
        blob = self._project.awb._awb.get_file_at(wf.index)
        self._set_status(f"Preview: AWB[{wf.index}] ({format_duration(wf.duration_s)})")
        self._preview.play_hca_bytes_async(
            blob,
            on_error=lambda msg: self.after(0, lambda: self._log_line(f"Preview failed: {msg}", "error")),
        )

    def _on_cue_select(self, event: tk.Event) -> None:
        if self._project is None:
            return
        sel = self._cue_tree.selection()
        if not sel:
            return
        cue_row = sel[0]
        # The cue_tree rows preserve insertion order which == cue index in cues().
        cue_idx = self._cue_tree.index(cue_row)
        cues = self._project.cues()
        if cue_idx >= len(cues):
            return
        cue = cues[cue_idx]

        # Highlight the waveform rows for the selected cue's table indices.
        target_rows = [
            rid for rid, tidx in self._wf_row_to_table_idx.items()
            if tidx in cue.waveform_indices
        ]
        self._wf_tree.selection_set(target_rows)
        if target_rows:
            self._wf_tree.see(target_rows[0])

    def _start(self) -> None:
        if self._running or self._project is None:
            return
        out_dir = self.out_dir_var.get().strip()
        if not out_dir:
            messagebox.showwarning("Missing output folder", "Choose an output folder first.")
            return

        self._stop_event.clear()
        self._set_running(True)
        self._progress.config(value=0, maximum=1)
        self._prog_label.config(text="")
        self._log_line(f"Extracting to {out_dir}", "info")

        threading.Thread(target=self._work, args=(out_dir,), daemon=True).start()

    def _stop(self) -> None:
        self._stop_event.set()
        self._set_status("Stopping…")

    def _work(self, out_dir: str) -> None:
        project = self._project
        assert project is not None
        try:
            written = project.extract_all_named(
                out_dir,
                progress_cb=lambda d, t: self.after(0, lambda: self._update_progress(d, t)),
                log_cb=lambda m, tag: self.after(0, lambda: self._log_line(m, tag)),
                stop_event=self._stop_event,
            )
            msg = f"Done — {len(written)} files written to {out_dir}"
            self.after(0, lambda: self._log_line(msg, "ok"))
            self.after(0, lambda: self._set_status(msg))
        except Exception as e:  # noqa: BLE001
            err = str(e)
            self.after(0, lambda: self._log_line(f"Extraction error: {err}", "error"))
            self.after(0, lambda: self._set_status("Extraction failed."))
        finally:
            self.after(0, lambda: self._set_running(False))

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
        self._start_btn.config(state="disabled" if running else ("normal" if self._project else "disabled"))
        self._stop_btn.config(state="normal" if running else "disabled")

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)
