from typing import Dict, List, Optional, Tuple

from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable

from ctf_solver.ui.textual.data.repo import fetch_jobs
from ctf_solver.ui.textual.utils import copy_to_clipboard, truncate_middle


class JobsTable(DataTable):
    class RowSelected(Message):
        def __init__(self, attempt_id: str) -> None:
            super().__init__()
            self.attempt_id = attempt_id

    current_attempt_id: Optional[str] = reactive(None)
    _attempt_id_to_flag: Dict[str, str] = {}
    _row_index_to_attempt_id: Dict[int, str] = {}
    _last_rows_signature: List[Tuple] = []

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.add_columns(
            "Attempt", "Challenge", "Status", "Steps", "Flag", "Last Action", "Started"
        )
        self.zebra_stripes = True
        self.cursor_type = "row"
        # Disable auto-sizing jitter: set fixed widths similar to Go TUI
        try:
            self.columns[0].width = 8
            self.columns[1].width = 20
            self.columns[2].width = 10
            self.columns[3].width = 6
            self.columns[4].width = 28
            self.columns[5].width = 24
            self.columns[6].width = 8
        except Exception:
            pass

    def _signature(self, rows: List[Tuple]) -> List[Tuple]:
        sig: List[Tuple] = []
        for (
            attempt_id,
            challenge,
            status,
            steps,
            started_at,
            last_action,
            last_output,
            flag,
        ) in rows:
            sig.append(
                (
                    str(attempt_id),
                    str(challenge),
                    str(status),
                    int(steps),
                    str(flag or ""),
                    str(last_action or ""),
                    started_at.strftime("%H:%M:%S") if hasattr(started_at, "strftime") else str(started_at),
                )
            )
        return sig

    def render_jobs(self, rows: List[Tuple]) -> None:
        prev_cursor_row = self.cursor_row
        prev_attempt_id = self.current_attempt_id

        # No-op if nothing changed
        sig = self._signature(rows)
        if sig == self._last_rows_signature:
            return

        # Clear only rows; columns remain as defined in on_mount
        self.clear()
        self._attempt_id_to_flag.clear()
        self._row_index_to_attempt_id.clear()
        for (
            attempt_id,
            challenge,
            status,
            steps,
            started_at,
            last_action,
            last_output,
            flag,
        ) in rows:
            attempt_short = attempt_id[:8]
            flag_short = flag if len(flag) <= 26 else flag[:26] + "…"
            self._attempt_id_to_flag[str(attempt_id)] = str(flag or "")
            self.add_row(
                attempt_short,
                str(challenge),
                str(status),
                str(steps),
                flag_short,
                truncate_middle(str(last_action or ""), 24),
                started_at.strftime("%H:%M:%S") if hasattr(started_at, "strftime") else str(started_at),
                key=attempt_id,
            )
            # Track mapping from visual row index to full attempt id
            row_idx = self.row_count - 1
            if row_idx >= 0:
                self._row_index_to_attempt_id[row_idx] = str(attempt_id)
        # Keep selection and scroll position if possible
        if self.row_count:
            target_idx: Optional[int] = None
            # Prefer previous attempt id
            if prev_attempt_id:
                for idx in range(self.row_count):
                    if self._row_index_to_attempt_id.get(idx) == prev_attempt_id:
                        target_idx = idx
                        break
            # Fallback to previous row index
            if target_idx is None and prev_cursor_row is not None and 0 <= prev_cursor_row < self.row_count:
                target_idx = prev_cursor_row
                prev_attempt_id = self._row_index_to_attempt_id.get(target_idx)

            if target_idx is None:
                target_idx = 0
                prev_attempt_id = self._row_index_to_attempt_id.get(0)

            # Only move cursor if changed to reduce event spam
            if self.cursor_row != target_idx:
                self.cursor_coordinate = (0, target_idx)

            # Update current_attempt_id without emitting unless it changed
            if prev_attempt_id and prev_attempt_id != self.current_attempt_id:
                self.current_attempt_id = prev_attempt_id
                self.post_message(self.RowSelected(self.current_attempt_id))

        # Update signature after render
        self._last_rows_signature = sig

    async def refresh_jobs(self) -> None:
        rows: List[Tuple] = fetch_jobs()
        self.render_jobs(rows)

    def action_copy_flag(self) -> None:
        if self.row_count == 0:
            return
        row_index = self.cursor_row
        if row_index is None:
            return
        # Prefer full flag via attempt_id mapping
        attempt_id = self._row_index_to_attempt_id.get(row_index, "")
        if attempt_id:
            full_flag = self._attempt_id_to_flag.get(attempt_id, "")
            if full_flag:
                copy_to_clipboard(full_flag)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:  # type: ignore
        # Update selected attempt id and notify
        if self.cursor_row is not None:
            self.current_attempt_id = self._row_index_to_attempt_id.get(self.cursor_row)
            if self.current_attempt_id:
                self.post_message(self.RowSelected(self.current_attempt_id))


