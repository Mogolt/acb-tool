"""Inject tab — replace one or more waveforms, save modified ACB + AWB."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.inject import InjectPlan, Replacement
from core.project import Project, ProjectLoadError

from . import theme as T
from .formatting import format_duration
from .preview import AudioPreview
from .widgets import folder_row


class InjectTab(tk.Frame):
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
        self._plan: InjectPlan | None = None
        self._saving_event = threading.Event()
        self._saving = False

        # waveform_tree row_id -> waveform table index
        self._wf_row_to_table_idx: dict[str, int] = {}
        # pending_tree row_id -> waveform table index
        self._pending_row_to_table_idx: dict[str, int] = {}

        self._build()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        mode_bar = tk.Frame(self, bg=T.BG)
        mode_bar.pack(fill="x", padx=20, pady=(10, 4))
        tk.Label(
            mode_bar, text="Inject", font=T.FONT_BIG, bg=T.BG, fg=T.TEXT,
        ).pack(side="left")
        tk.Label(
            mode_bar, text="(replace waveforms → rebuild AWB → patch ACB → save)",
            font=T.FONT_SM, bg=T.BG, fg=T.MUTED,
        ).pack(side="left", padx=(10, 0), pady=(6, 0))

        folder_row(
            self, "ACB file (input):", self.acb_path_var, self._browse_acb,
            hint="Companion .awb must sit beside it.",
        )
        folder_row(
            self, "Output folder:", self.out_dir_var, self._browse_out,
            hint="Modified core.acb + core.awb (same filenames) land here.",
        )

        tk.Frame(self, bg=T.PANEL, height=1).pack(fill="x", padx=16, pady=(8, 8))

        # Waveform list
        wf_outer = tk.Frame(self, bg=T.BG)
        wf_outer.pack(fill="both", expand=True, padx=20, pady=(0, 4))
        tk.Label(
            wf_outer, text="Waveforms  (select one, then Replace…)",
            font=T.FONT, bg=T.BG, fg=T.MUTED,
        ).pack(anchor="w")

        cols = ("wf_tidx", "cue", "awbid", "ch", "rate", "duration", "pending")
        self._wf_tree = ttk.Treeview(wf_outer, columns=cols, show="headings", height=10)
        for cid, label, w in [
            ("wf_tidx",  "Wf#",           50),
            ("cue",      "Cue name(s)",   260),
            ("awbid",    "AWB Id",        60),
            ("ch",       "Ch",            40),
            ("rate",     "Rate (Hz)",     80),
            ("duration", "Duration",      80),
            ("pending",  "Pending",       90),
        ]:
            self._wf_tree.heading(cid, text=label)
            self._wf_tree.column(cid, width=w, anchor="w")
        self._wf_tree.pack(side="left", fill="both", expand=True)
        wf_sb = tk.Scrollbar(wf_outer, command=self._wf_tree.yview, bg=T.PANEL,
                             troughcolor=T.PANEL, relief="flat")
        wf_sb.pack(side="right", fill="y")
        self._wf_tree.configure(yscrollcommand=wf_sb.set)
        self._wf_tree.bind("<<TreeviewSelect>>", self._on_wf_select)
        # Double-click previews source audio. Explicit Replace button handles
        # the injection flow — double-click as "open file dialog" was a trap.
        self._wf_tree.bind("<Double-Button-1>", lambda _e: self._preview_source())

        # Action buttons
        act = tk.Frame(self, bg=T.BG)
        act.pack(fill="x", padx=20, pady=(4, 4))
        self._replace_btn = tk.Button(
            act, text="↻  Replace with WAV…", font=T.FONT,
            bg=T.PANEL, fg=T.TEXT,
            activebackground=T.ACCENT, activeforeground=T.TEXT,
            relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
            command=self._replace_selected, state="disabled",
        )
        self._replace_btn.pack(side="left", padx=(0, 6))
        self._remove_pending_btn = tk.Button(
            act, text="–  Remove from pending", font=T.FONT,
            bg=T.PANEL, fg=T.MUTED,
            activebackground="#2a2a4e", activeforeground=T.TEXT,
            relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
            command=self._remove_pending_selected, state="disabled",
        )
        self._remove_pending_btn.pack(side="left", padx=(0, 6))

        tk.Button(
            act, text="♪  Preview source", font=T.FONT,
            bg=T.PANEL, fg=T.TEXT,
            activebackground=T.ACCENT, activeforeground=T.TEXT,
            relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
            command=self._preview_source,
        ).pack(side="left", padx=(12, 6))

        tk.Button(
            act, text="♪  Preview replacement", font=T.FONT,
            bg=T.PANEL, fg=T.TEXT,
            activebackground=T.ACCENT, activeforeground=T.TEXT,
            relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
            command=self._preview_replacement,
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            act, text="■  Stop preview", font=T.FONT,
            bg=T.PANEL, fg=T.MUTED,
            activebackground="#2a2a4e", activeforeground=T.TEXT,
            relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
            command=self._preview.stop,
        ).pack(side="left", padx=(0, 6))

        self._install_tree_style()

        # Pending replacements panel
        tk.Frame(self, bg=T.PANEL, height=1).pack(fill="x", padx=16, pady=(6, 6))
        pend_outer = tk.Frame(self, bg=T.BG)
        pend_outer.pack(fill="x", padx=20, pady=(0, 4))
        tk.Label(
            pend_outer, text="Pending replacements",
            font=T.FONT, bg=T.BG, fg=T.MUTED,
        ).pack(anchor="w")

        pend_cols = ("wf_tidx", "cue", "src", "fmt")
        self._pending_tree = ttk.Treeview(pend_outer, columns=pend_cols, show="headings", height=4)
        for cid, label, w in [
            ("wf_tidx", "Wf#",          50),
            ("cue",     "Cue name(s)",  220),
            ("src",     "Replacement",  280),
            ("fmt",     "New format",   170),
        ]:
            self._pending_tree.heading(cid, text=label)
            self._pending_tree.column(cid, width=w, anchor="w")
        self._pending_tree.pack(side="left", fill="x", expand=True)
        self._pending_tree.bind("<<TreeviewSelect>>", self._on_pending_select)
        self._pending_tree.bind("<Double-Button-1>", lambda _e: self._preview_replacement())

        # Progress + log
        self._progress = ttk.Progressbar(
            self, style="Custom.Horizontal.TProgressbar", mode="indeterminate",
        )
        self._progress.pack(fill="x", padx=20, pady=(6, 2))

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
        self._log.tag_configure("warn",  foreground=T.WARNING)
        self._log.tag_configure("info",  foreground=T.MUTED)

        # Save button
        btns = tk.Frame(self, bg=T.BG)
        btns.pack(fill="x", padx=20, pady=(2, 10), anchor="w")
        self._save_btn = tk.Button(
            btns, text="▶  Save modified bank", font=T.FONT,
            bg=T.ACCENT, fg=T.TEXT,
            activebackground=T.ACCENT_HOVER, activeforeground=T.TEXT,
            relief="flat", bd=0, padx=14, pady=8, cursor="hand2",
            command=self._save, state="disabled",
        )
        self._save_btn.pack(side="left")

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

    # ── ACB loading ───────────────────────────────────────────────────────────

    def _browse_acb(self) -> None:
        path = filedialog.askopenfilename(
            title="Open ACB",
            filetypes=[("ACB files", "*.acb"), ("All files", "*.*")],
        )
        if not path:
            return
        self.acb_path_var.set(path)
        if not self.out_dir_var.get():
            self.out_dir_var.set(str(Path(path).parent / (Path(path).parent.name + "_modified")))
        self._load_project(path)

    def _browse_out(self) -> None:
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.out_dir_var.set(path)

    def _load_project(self, path: str) -> None:
        self._wf_tree.delete(*self._wf_tree.get_children())
        self._pending_tree.delete(*self._pending_tree.get_children())
        self._wf_row_to_table_idx.clear()
        self._pending_row_to_table_idx.clear()
        self._project = None
        self._plan = None
        self._replace_btn.config(state="disabled")
        self._save_btn.config(state="disabled")

        try:
            project = Project.open(path)
        except ProjectLoadError as e:
            messagebox.showerror("Open ACB failed", str(e))
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Open ACB failed", f"{e}")
            return

        self._project = project
        self._plan = InjectPlan(project)

        # Pre-compute cue labels by waveform_table_index (there may be multiple
        # cues pointing at the same waveform, or none).
        cue_labels: dict[int, list[str]] = {}
        for cue in project.cues():
            for wf_tidx in cue.waveform_indices:
                cue_labels.setdefault(wf_tidx, []).append(cue.name)

        for table_idx, w in enumerate(project.waveforms()):
            cues_for_this = cue_labels.get(table_idx, [])
            cue_display = ", ".join(cues_for_this) if cues_for_this else "(no cue)"
            row = self._wf_tree.insert(
                "", "end",
                values=(
                    table_idx,
                    cue_display,
                    w.index,
                    w.channels,
                    w.sample_rate,
                    format_duration(w.duration_s),
                    "",
                ),
            )
            self._wf_row_to_table_idx[row] = table_idx

        summary = (
            f"{project.acb.path.name}  +  {project.awb.path.name}  "
            f"— {len(project.cues())} cues, {len(project.waveforms())} waveforms"
        )
        self._set_status(summary)
        self._log_line(f"Opened {project.acb.path}", "info")
        self._log_line(f"Paired  {project.awb.path}", "info")

    # ── selection + replace ───────────────────────────────────────────────────

    def _on_wf_select(self, _event: tk.Event) -> None:
        has = bool(self._wf_tree.selection()) and self._project is not None
        self._replace_btn.config(state="normal" if has else "disabled")

    def _preview_source(self) -> None:
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
        try:
            blob = self._project.awb._awb.get_file_at(wf.index)
        except Exception as e:  # noqa: BLE001
            self._log_line(f"Preview failed: {e}", "error")
            return
        self._set_status(f"Preview source: wf[{table_idx}] AWB[{wf.index}]")
        self._preview.play_hca_bytes_async(
            blob,
            on_error=lambda msg: self.after(0, lambda: self._log_line(f"Preview failed: {msg}", "error")),
        )

    def _preview_replacement(self) -> None:
        """Preview the replacement WAV for whichever row is selected.

        If a pending row is selected, preview that. Else if a waveform row is
        selected and has a queued replacement, preview it.
        """
        if self._plan is None:
            return
        table_idx: int | None = None
        pend_sel = self._pending_tree.selection()
        if pend_sel:
            table_idx = self._pending_row_to_table_idx.get(pend_sel[0])
        else:
            wf_sel = self._wf_tree.selection()
            if wf_sel:
                candidate = self._wf_row_to_table_idx.get(wf_sel[0])
                if candidate is not None and candidate in {r.waveform_table_index for r in self._plan.pending()}:
                    table_idx = candidate
        if table_idx is None:
            self._set_status("Select a pending replacement (or a waveform that has one queued) to preview.")
            return
        replacement = next(
            (r for r in self._plan.pending() if r.waveform_table_index == table_idx), None,
        )
        if replacement is None:
            return
        self._set_status(f"Preview replacement: {Path(replacement.replacement_wav_path).name}")
        self._preview.play_path_async(
            replacement.replacement_wav_path,
            on_error=lambda msg: self.after(0, lambda: self._log_line(f"Preview failed: {msg}", "error")),
        )

    def _on_pending_select(self, _event: tk.Event) -> None:
        has = bool(self._pending_tree.selection())
        self._remove_pending_btn.config(state="normal" if has else "disabled")

    def _replace_selected(self) -> None:
        if self._project is None or self._plan is None:
            return
        sel = self._wf_tree.selection()
        if not sel:
            return
        row = sel[0]
        table_idx = self._wf_row_to_table_idx[row]

        wav_path = filedialog.askopenfilename(
            title="Pick replacement WAV",
            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")],
        )
        if not wav_path:
            return

        try:
            r = Replacement.from_wav(
                waveform_table_index=table_idx,
                wav_path=wav_path,
            )
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Encode failed", f"{e}")
            self._log_line(f"  encode failed for wf[{table_idx}]: {e}", "error")
            return

        # Format notes — distinguished so the user knows which are harmless
        # (auto-resample handles it) vs which might actually cause trouble
        # (channel mismatch has no auto-fix yet).
        src_wf = self._project.waveforms()[table_idx]
        if src_wf.sample_rate and src_wf.sample_rate != r.new_sample_rate:
            self._log_line(
                f"  auto-resample wf[{table_idx}]: "
                f"{r.new_sample_rate} Hz → {src_wf.sample_rate} Hz on Save "
                f"(matches source bank; required for Switch playback)",
                "info",
            )
        if src_wf.channels and src_wf.channels != r.new_channels:
            self._log_line(
                f"  ⚠ channel mismatch on wf[{table_idx}]: "
                f"{r.new_channels} ch vs source {src_wf.channels} ch — "
                f"may cause playback issues in-game",
                "warn",
            )

        self._plan.add(r)
        self._refresh_pending_tree()
        self._update_pending_markers()
        self._save_btn.config(state="normal")
        self._log_line(
            f"  queued wf[{table_idx}] ← {Path(wav_path).name}  "
            f"({r.new_channels}ch {r.new_sample_rate}Hz {r.new_sample_count} samp)",
            "ok",
        )

    def _remove_pending_selected(self) -> None:
        if self._plan is None:
            return
        sel = self._pending_tree.selection()
        if not sel:
            return
        row = sel[0]
        table_idx = self._pending_row_to_table_idx.get(row)
        if table_idx is None:
            return
        self._plan.remove(table_idx)
        self._refresh_pending_tree()
        self._update_pending_markers()
        self._save_btn.config(state="normal" if self._plan.pending() else "disabled")
        self._remove_pending_btn.config(state="disabled")

    def _refresh_pending_tree(self) -> None:
        self._pending_tree.delete(*self._pending_tree.get_children())
        self._pending_row_to_table_idx.clear()
        if self._plan is None or self._project is None:
            return

        cue_labels: dict[int, list[str]] = {}
        for cue in self._project.cues():
            for wf_tidx in cue.waveform_indices:
                cue_labels.setdefault(wf_tidx, []).append(cue.name)

        for r in self._plan.pending():
            cues_for_this = cue_labels.get(r.waveform_table_index, [])
            cue_display = ", ".join(cues_for_this) if cues_for_this else "(no cue)"
            fmt = f"{r.new_channels}ch {r.new_sample_rate}Hz {r.new_sample_count:,} samp"
            row = self._pending_tree.insert(
                "", "end",
                values=(
                    r.waveform_table_index,
                    cue_display,
                    Path(r.replacement_wav_path).name,
                    fmt,
                ),
            )
            self._pending_row_to_table_idx[row] = r.waveform_table_index

    def _update_pending_markers(self) -> None:
        """Mark pending waveform rows in the main list with a ● glyph."""
        if self._plan is None:
            return
        pending_set = {r.waveform_table_index for r in self._plan.pending()}
        for row_id, table_idx in self._wf_row_to_table_idx.items():
            values = list(self._wf_tree.item(row_id, "values"))
            if len(values) < 7:
                continue
            values[6] = "●  queued" if table_idx in pending_set else ""
            self._wf_tree.item(row_id, values=values)

    # ── save (apply) ──────────────────────────────────────────────────────────

    def _save(self) -> None:
        if self._saving or self._project is None or self._plan is None:
            return
        if not self._plan.pending():
            return
        out_dir = self.out_dir_var.get().strip()
        if not out_dir:
            messagebox.showwarning("Missing output folder", "Choose an output folder first.")
            return

        out_acb_path = Path(out_dir) / self._project.acb.path.name
        out_awb_path = Path(out_dir) / self._project.awb.path.name

        # Warn if overwriting the source bank.
        src_acb = self._project.acb.path.resolve()
        src_awb = self._project.awb.path.resolve()
        if out_acb_path.resolve() == src_acb or out_awb_path.resolve() == src_awb:
            if not messagebox.askyesno(
                "Overwrite source bank?",
                f"The output path is the same as the source bank. "
                f"Overwrite {src_acb.name} and {src_awb.name}?",
            ):
                return

        self._set_saving(True)
        self._progress.start(12)
        self._log_line(
            f"Saving modified bank ({len(self._plan.pending())} replacement(s)) → {out_dir}",
            "info",
        )
        threading.Thread(
            target=self._save_worker,
            args=(out_acb_path, out_awb_path),
            daemon=True,
        ).start()

    def _save_worker(self, out_acb_path: Path, out_awb_path: Path) -> None:
        assert self._plan is not None
        try:
            out_acb_path.parent.mkdir(parents=True, exist_ok=True)
            result = self._plan.apply()
            out_acb_path.write_bytes(result.modified_acb_bytes)
            out_awb_path.write_bytes(result.modified_awb_bytes)
            msg = (
                f"Wrote {out_acb_path.name} ({len(result.modified_acb_bytes):,} B) + "
                f"{out_awb_path.name} ({len(result.modified_awb_bytes):,} B)  "
                f"— {result.replacements_applied} replacement(s) applied."
            )
            self.after(0, lambda: self._log_line(msg, "ok"))
            self.after(0, lambda: self._set_status(f"Saved → {out_acb_path.parent}"))
            # Replacements are on disk now — drop them from the queue so the
            # UI reflects "nothing pending" state (no more ● markers, empty
            # Pending Replacements panel, Save button disabled).
            self.after(0, self._clear_plan_post_save)
        except Exception as e:  # noqa: BLE001
            err = str(e)
            self.after(0, lambda: self._log_line(f"Save failed: {err}", "error"))
            self.after(0, lambda: self._set_status("Save failed."))
        finally:
            self.after(0, lambda: (self._progress.stop(), self._set_saving(False)))

    def _clear_plan_post_save(self) -> None:
        if self._plan is None:
            return
        self._plan.clear()
        self._refresh_pending_tree()
        self._update_pending_markers()
        self._remove_pending_btn.config(state="disabled")

    # ── bookkeeping ───────────────────────────────────────────────────────────

    def _log_line(self, msg: str, tag: str = "info") -> None:
        self._log.config(state="normal")
        self._log.insert("end", msg + "\n", tag)
        self._log.see("end")
        self._log.config(state="disabled")

    def _set_saving(self, saving: bool) -> None:
        self._saving = saving
        self._save_btn.config(state="disabled" if saving else
                              ("normal" if self._plan and self._plan.pending() else "disabled"))
        self._replace_btn.config(state="disabled" if saving else self._replace_btn["state"])

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)
