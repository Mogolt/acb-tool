"""Full Project Mode coordinator: ACB + AWB paired by filename stem.

Opens an ACB, auto-locates its companion AWB in the same directory, exposes
cue-level and waveform-level read access, and extracts named WAVs (cue name
as filename, multi-waveform cues disambiguated with an index suffix).
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Callable

from PyCriCodecsEx.hca import HCACodec

from .acb import AcbReader
from .awb import AwbReader
from .models import Cue, Waveform


ProgressCb = Callable[[int, int], None]
LogCb = Callable[[str, str], None]


class ProjectLoadError(Exception):
    pass


_SANITIZE_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def _sanitize_filename(name: str) -> str:
    cleaned = _SANITIZE_RE.sub("_", name).strip(" .")
    return cleaned or "cue"


class Project:
    """One ACB+AWB pair. Use `Project.open(acb_path)` to construct."""

    def __init__(self, acb: AcbReader, awb: AwbReader) -> None:
        self.acb = acb
        self.awb = awb

    @classmethod
    def open(cls, acb_path: str | os.PathLike[str]) -> "Project":
        acb = AcbReader(acb_path)
        awb_path = acb.paired_awb_path()
        if not awb_path.is_file():
            raise ProjectLoadError(
                f"No companion AWB at {awb_path}. "
                f"ACB Tool expects {acb.path.name} and {awb_path.name} in the same folder."
            )
        awb = AwbReader(awb_path)
        return cls(acb, awb)

    # ── read-only views ───────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self.acb.name

    def cues(self) -> tuple[Cue, ...]:
        return self.acb.cues()

    def waveforms(self) -> tuple[Waveform, ...]:
        return self.acb.waveforms()

    # ── named extraction ──────────────────────────────────────────────────────

    def extract_all_named(
        self,
        out_dir: str | os.PathLike[str],
        *,
        progress_cb: ProgressCb | None = None,
        log_cb: LogCb | None = None,
        stop_event: threading.Event | None = None,
    ) -> list[Path]:
        """Extract every cue to WAV named after the cue.

        Cues that resolve to multiple waveforms get a ``_NN`` suffix. Cues that
        resolve to zero waveforms are skipped (orphan cue graph).
        """
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)

        cues = self.cues()
        waveforms = self.waveforms()
        wf_by_table_index = {i: wf for i, wf in enumerate(waveforms)}

        # Pre-compute total extract actions so progress is accurate.
        tasks: list[tuple[str, int]] = []  # (output_stem, awb_idx)
        seen_names: dict[str, int] = {}
        for cue in cues:
            if not cue.waveform_indices:
                continue
            base = _sanitize_filename(cue.name)
            multi = len(cue.waveform_indices) > 1
            for k, table_idx in enumerate(cue.waveform_indices):
                wf = wf_by_table_index.get(table_idx)
                if wf is None:
                    continue
                stem = f"{base}_{k:02d}" if multi else base
                # Disambiguate if another cue shared the same name.
                if stem in seen_names:
                    seen_names[stem] += 1
                    stem = f"{stem}__{seen_names[stem]:02d}"
                else:
                    seen_names[stem] = 0
                tasks.append((stem, wf.index))

        written: list[Path] = []
        total = len(tasks)
        for i, (stem, awb_idx) in enumerate(tasks):
            if stop_event is not None and stop_event.is_set():
                break
            out_path = out / f"{stem}.wav"
            try:
                blob = self.awb._awb.get_file_at(awb_idx)
                HCACodec(blob).save(str(out_path))
                written.append(out_path)
                if log_cb:
                    log_cb(f"  extracted {out_path.name}", "ok")
            except Exception as e:  # noqa: BLE001
                if log_cb:
                    log_cb(f"  failed {stem}: {e}", "error")
            if progress_cb:
                progress_cb(i + 1, total)

        return written
