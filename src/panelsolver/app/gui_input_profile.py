"""Opt-in timing records for one synchronous GUI input-file load."""

from __future__ import annotations

import os
import time
from collections import Counter
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GUI_INPUT_PROFILE_ENV = "PANELSOLVER_GUI_PROFILE"
GUI_INPUT_PATH_MODE_ENV = "PANELSOLVER_GUI_PATH_MODE"
GUI_INPUT_PATH_MODES = frozenset({"baseline", "stl_cache", "all_path_cache"})
_FALSE_ENV_VALUES = frozenset({"", "0", "false", "no", "off"})


def gui_input_profiling_enabled() -> bool:
    """Return whether the opt-in GUI input profiler is enabled."""
    return os.environ.get(GUI_INPUT_PROFILE_ENV, "").strip().lower() not in (
        _FALSE_ENV_VALUES
    )


def gui_input_path_mode() -> str:
    """Return the selected one-load path-cache experiment mode."""
    mode = os.environ.get(GUI_INPUT_PATH_MODE_ENV, "baseline").strip().lower()
    mode = mode or "baseline"
    if mode not in GUI_INPUT_PATH_MODES:
        choices = ", ".join(sorted(GUI_INPUT_PATH_MODES))
        raise ValueError(
            f"{GUI_INPUT_PATH_MODE_ENV} must be one of: {choices}; got {mode!r}."
        )
    return mode


@dataclass(slots=True)
class _StlPathAccess:
    entries: int = 0
    exists_calls: int = 0
    resolve_calls: int = 0
    cache_hits: int = 0


@dataclass(slots=True)
class _OutDirAccess:
    entries: int = 0
    resolve_calls: int = 0
    cache_hits: int = 0


@dataclass(slots=True)
class GuiInputProfile:
    """Accumulate timings without changing the measured call sequence."""

    input_path: Path
    started_at: float = field(default_factory=time.perf_counter)
    timings: dict[tuple[str, str], float] = field(default_factory=dict)
    stl_paths: dict[str, _StlPathAccess] = field(default_factory=dict)
    stl_exists_total: float = 0.0
    stl_resolve_total: float = 0.0
    out_dirs: dict[str, _OutDirAccess] = field(default_factory=dict)
    path_mode: str = "baseline"
    rows: int | None = None
    columns: int | None = None
    thread_name: str | None = None
    qt_gui_thread: bool | None = None
    status: str = "running"
    _finished_at: float | None = None

    def add_timing(self, scope: str, name: str, elapsed: float) -> None:
        key = (scope, name)
        self.timings[key] = self.timings.get(key, 0.0) + elapsed

    def note_stl_entry(self, path: Path) -> None:
        self.stl_paths.setdefault(str(path), _StlPathAccess()).entries += 1

    def note_stl_exists(self, path: Path, elapsed: float) -> None:
        stats = self.stl_paths.setdefault(str(path), _StlPathAccess())
        stats.exists_calls += 1
        self.stl_exists_total += elapsed

    def note_stl_resolve(self, path: Path, elapsed: float) -> None:
        stats = self.stl_paths.setdefault(str(path), _StlPathAccess())
        stats.resolve_calls += 1
        self.stl_resolve_total += elapsed

    def note_stl_cache_hit(self, path: Path) -> None:
        self.stl_paths.setdefault(str(path), _StlPathAccess()).cache_hits += 1

    def note_out_dir_entry(self, key: str) -> None:
        self.out_dirs.setdefault(key, _OutDirAccess()).entries += 1

    def note_out_dir_resolve(self, key: str) -> None:
        self.out_dirs.setdefault(key, _OutDirAccess()).resolve_calls += 1

    def note_out_dir_cache_hit(self, key: str) -> None:
        self.out_dirs.setdefault(key, _OutDirAccess()).cache_hits += 1

    def finish(self, status: str) -> None:
        if self._finished_at is None:
            self._finished_at = time.perf_counter()
        self.status = status

    def format_lines(self) -> tuple[str, ...]:
        finished_at = self._finished_at or time.perf_counter()
        total = finished_at - self.started_at
        cells = (
            self.rows * self.columns
            if self.rows is not None and self.columns is not None
            else None
        )
        lines = [f"[PROFILE][GUI_INPUT] file={str(self.input_path)!r}"]
        lines.append(f"[PROFILE][GUI_INPUT] path_mode={self.path_mode}")
        if self.thread_name is not None:
            gui_thread = str(bool(self.qt_gui_thread)).lower()
            lines.append(
                f"[PROFILE][GUI_INPUT] thread={self.thread_name!r} "
                f"qt_gui_thread={gui_thread}"
            )
        if self.rows is not None and self.columns is not None:
            lines.append(
                f"[PROFILE][GUI_INPUT] rows={self.rows} columns={self.columns} "
                f"cells={cells}"
            )
        lines.append(
            f"[PROFILE][GUI_INPUT] total={total:.6f} s status={self.status}"
        )

        order = (
            ("GUI_INPUT", "read_cases"),
            ("GUI_INPUT", "materialize_raw_rows"),
            ("GUI_INPUT", "validate_row_mappings"),
            ("GUI_INPUT", "mapping_to_dict"),
            ("GUI_INPUT", "update_loaded_state"),
            ("GUI_INPUT", "populate_table"),
            ("GUI_INPUT", "update_post_table_state"),
            ("GUI_INPUT", "emit_input_path_changed"),
            ("GUI_INPUT", "emit_cases_updated"),
            ("GUI_ADAPTER", "read_case_table"),
            ("GUI_ADAPTER", "dataframe_to_records"),
            ("CASE_IO", "read_case_table_total"),
            ("CASE_IO", "pandas_read_csv"),
            ("CASE_IO", "pandas_read_excel"),
            ("CASE_IO", "schema_checks"),
            ("CASE_IO", "defaults"),
            ("CASE_IO", "validate_total"),
            ("CASE_IO", "column_order"),
            ("CASE_IO", "validate_case_ids"),
            ("CASE_IO", "stl_path_validation"),
            ("CASE_IO", "validate_required_numeric"),
            ("CASE_IO", "validate_optional_numeric"),
            ("CASE_IO", "validate_positive_columns"),
            ("CASE_IO", "product_validate_rows"),
            ("CASE_IO", "validate_flags"),
            ("CASE_IO", "validate_ray_backend"),
            ("CASE_IO", "validate_attitude"),
            ("CASE_IO", "validate_attitude_domain"),
            ("CASE_IO", "validate_out_dir"),
            ("CASE_IO", "resolve_out_dirs"),
            ("TABLE", "column_determination"),
            ("TABLE", "reset_and_headers"),
            ("TABLE", "create_items_and_set"),
            ("TABLE", "resize_columns"),
            ("TABLE", "stl_column_width"),
            ("TABLE", "summary_update"),
        )
        emitted: set[tuple[str, str]] = set()
        for key in order:
            if key in self.timings:
                lines.append(
                    f"[PROFILE][{key[0]}] {key[1]}={self.timings[key]:.6f} s"
                )
                emitted.add(key)
        for key in sorted(self.timings.keys() - emitted):
            lines.append(
                f"[PROFILE][{key[0]}] {key[1]}={self.timings[key]:.6f} s"
            )

        if self.stl_paths:
            entries = sum(stats.entries for stats in self.stl_paths.values())
            exists_calls = sum(
                stats.exists_calls for stats in self.stl_paths.values()
            )
            resolve_calls = sum(
                stats.resolve_calls for stats in self.stl_paths.values()
            )
            cache_hits = sum(stats.cache_hits for stats in self.stl_paths.values())
            lines.extend(
                (
                    (
                        f"[PROFILE][STL_PATH] entries={entries} "
                        f"unique={len(self.stl_paths)} cache_hits={cache_hits}"
                    ),
                    (
                        f"[PROFILE][STL_PATH] exists_total="
                        f"{self.stl_exists_total:.6f} s calls={exists_calls}"
                    ),
                    (
                        f"[PROFILE][STL_PATH] resolve_total="
                        f"{self.stl_resolve_total:.6f} s calls={resolve_calls}"
                    ),
                )
            )
            histogram = Counter(stats.entries for stats in self.stl_paths.values())
            histogram_text = ",".join(
                f"{calls}_calls:{path_count}_paths"
                for calls, path_count in sorted(histogram.items())
            )
            lines.append(
                f"[PROFILE][STL_PATH] entry_repetition_histogram={histogram_text}"
            )
            repeated = sorted(
                (
                    (path, stats)
                    for path, stats in self.stl_paths.items()
                    if stats.entries > 1
                ),
                key=lambda pair: (-pair[1].entries, pair[0]),
            )
            for path, stats in repeated[:20]:
                lines.append(
                    f"[PROFILE][STL_PATH] repeated_path={path!r} "
                    f"entries={stats.entries} exists_calls={stats.exists_calls} "
                    f"resolve_calls={stats.resolve_calls} "
                    f"cache_hits={stats.cache_hits}"
                )
            if len(repeated) > 20:
                lines.append(
                    f"[PROFILE][STL_PATH] repeated_paths_omitted="
                    f"{len(repeated) - 20}"
                )
        if self.out_dirs:
            entries = sum(stats.entries for stats in self.out_dirs.values())
            resolve_calls = sum(
                stats.resolve_calls for stats in self.out_dirs.values()
            )
            cache_hits = sum(stats.cache_hits for stats in self.out_dirs.values())
            lines.append(
                f"[PROFILE][OUT_DIR] entries={entries} "
                f"unique={len(self.out_dirs)} resolve_calls={resolve_calls} "
                f"cache_hits={cache_hits}"
            )
        return tuple(lines)


_CURRENT_PROFILE: ContextVar[GuiInputProfile | None] = ContextVar(
    "panelsolver_gui_input_profile",
    default=None,
)


def current_gui_input_profile() -> GuiInputProfile | None:
    return _CURRENT_PROFILE.get()


def activate_gui_input_profile(profile: GuiInputProfile) -> Token:
    return _CURRENT_PROFILE.set(profile)


def deactivate_gui_input_profile(token: Token) -> None:
    _CURRENT_PROFILE.reset(token)


def timed_call[T](
    profile: GuiInputProfile | None,
    scope: str,
    name: str,
    callback: Callable[..., T],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Call once and record elapsed time when a profile is active."""
    if profile is None:
        return callback(*args, **kwargs)
    started_at = time.perf_counter()
    try:
        return callback(*args, **kwargs)
    finally:
        profile.add_timing(scope, name, time.perf_counter() - started_at)


__all__ = (
    "GUI_INPUT_PATH_MODES",
    "GUI_INPUT_PATH_MODE_ENV",
    "GUI_INPUT_PROFILE_ENV",
    "GuiInputProfile",
    "activate_gui_input_profile",
    "current_gui_input_profile",
    "deactivate_gui_input_profile",
    "gui_input_path_mode",
    "gui_input_profiling_enabled",
    "timed_call",
)
