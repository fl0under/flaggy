from typing import Dict, List, Optional, Tuple
import asyncio

from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable
from textual.containers import Vertical

from ctf_solver.ui.textual.data.repo import fetch_challenge_runs, fetch_logs
from ctf_solver.ui.textual.widgets.log_panel import LogPanel


class RunsTable(DataTable):
    class RunSelected(Message):
        def __init__(self, attempt_id: str) -> None:
            super().__init__()
            self.attempt_id = attempt_id

    current_attempt_id: Optional[str] = reactive(None)
    current_challenge_id: Optional[int] = reactive(None)
    _attempt_id_to_flag: Dict[str, str] = {}
    _row_index_to_attempt_id: Dict[int, str] = {}
    _attempt_id_to_status: Dict[str, str] = {}
    _last_rows_signature: List[Tuple] = []

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.border_title = "Challenge Runs"
        self.add_columns("Attempt", "Status", "Steps", "Flag", "Started")
        self.zebra_stripes = True
        
        # Set column widths
        try:
            self.columns[0].width = 8
            self.columns[1].width = 10
            self.columns[2].width = 6
            self.columns[3].width = 28
            self.columns[4].width = 12
        except Exception:
            pass

    def _signature(self, rows: List[Tuple]) -> List[Tuple]:
        sig: List[Tuple] = []
        for (attempt_id, status, started_at, flag, steps) in rows:
            sig.append((
                str(attempt_id),
                str(status),
                int(steps),
                str(flag or ""),
                started_at.strftime("%H:%M:%S") if hasattr(started_at, "strftime") else str(started_at),
            ))
        return sig

    def render_runs(self, runs: List[Tuple]) -> None:
        prev_cursor_row = self.cursor_row
        prev_attempt_id = self.current_attempt_id

        # No-op if nothing changed
        sig = self._signature(runs)
        if sig == self._last_rows_signature:
            return

        # Clear only rows; columns remain as defined in on_mount
        self.clear()
        self._attempt_id_to_flag.clear()
        self._row_index_to_attempt_id.clear()
        self._attempt_id_to_status.clear()

        for (attempt_id, status, started_at, flag, steps) in runs:
            attempt_short = attempt_id[:8]
            flag_short = flag if len(flag) <= 26 else flag[:26] + "…"
            self._attempt_id_to_flag[str(attempt_id)] = str(flag or "")
            self._attempt_id_to_status[str(attempt_id)] = str(status)
            
            self.add_row(
                attempt_short,
                str(status),
                str(steps),
                flag_short,
                started_at.strftime("%H:%M:%S") if hasattr(started_at, "strftime") else str(started_at),
                key=attempt_id,
            )
            
            # Track mapping from visual row index to full attempt id
            row_idx = self.row_count - 1
            if row_idx >= 0:
                self._row_index_to_attempt_id[row_idx] = str(attempt_id)

        # Keep selection and scroll position if possible
        if self.row_count > 0:
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
                self.post_message(self.RunSelected(self.current_attempt_id))

        # Update signature after render
        self._last_rows_signature = sig

    async def refresh_runs_for_challenge(self, challenge_id: int) -> None:
        """Refresh runs for specific challenge"""
        self.current_challenge_id = challenge_id
        runs: List[Tuple] = await asyncio.to_thread(fetch_challenge_runs, challenge_id)
        self.render_runs(runs)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        # Update selected attempt id and notify
        if self.cursor_row is not None:
            self.current_attempt_id = self._row_index_to_attempt_id.get(self.cursor_row)
            if self.current_attempt_id:
                self.post_message(self.RunSelected(self.current_attempt_id))
            if self._selection_callback:
                self._selection_callback()

    def set_selection_callback(self, callback):
        self._selection_callback = callback

    def get_selected_attempt(self) -> Optional[str]:
        return self.current_attempt_id

    def get_attempt_status(self, attempt_id: Optional[str]) -> Optional[str]:
        if attempt_id is None:
            return None
        return self._attempt_id_to_status.get(attempt_id)


class ChallengeRunsPanel(Vertical):
    current_challenge_id: Optional[int] = reactive(None)
    current_challenge_name: str = reactive("")

    def compose(self):
        self.runs_table = RunsTable()
        self.runs_table.set_selection_callback(self._notify_selection_change)
        yield self.runs_table
        
        self.log_panel = LogPanel()
        yield self.log_panel

    def on_mount(self) -> None:
        # Set up layout proportions
        self.border_title = "No Challenge Selected"

    async def update_challenge(self, challenge_id: int, challenge_name: str) -> None:
        """Update to show runs for a specific challenge"""
        self.current_challenge_id = challenge_id
        self.current_challenge_name = challenge_name
        self.border_title = f"Challenge: {challenge_name}"
        
        # Refresh runs for this challenge
        await self.runs_table.refresh_runs_for_challenge(challenge_id)
        
        # Clear log panel until a run is selected
        self.log_panel.render_logs([])

    async def on_runs_table_run_selected(self, event: RunsTable.RunSelected) -> None:
        """Handle run selection - show logs for selected run"""
        await self.log_panel.refresh_logs(event.attempt_id)

    def action_copy_flag(self) -> None:
        """Copy flag from currently selected run"""
        self.runs_table._attempt_id_to_flag
        if self.runs_table.row_count == 0:
            return
        row_index = self.runs_table.cursor_row
        if row_index is None:
            return
        # Get full flag via attempt_id mapping
        attempt_id = self.runs_table._row_index_to_attempt_id.get(row_index, "")
        if attempt_id:
            full_flag = self.runs_table._attempt_id_to_flag.get(attempt_id, "")
            if full_flag:
                from ctf_solver.ui.textual.utils import copy_to_clipboard
                copy_to_clipboard(full_flag)

    def get_selected_attempt(self) -> Optional[str]:
        return self.runs_table.get_selected_attempt()

    def get_selected_attempt_status(self) -> Optional[str]:
        return self.runs_table.get_attempt_status(self.runs_table.get_selected_attempt())

    def get_current_challenge(self) -> tuple[Optional[int], Optional[str]]:
        return self.current_challenge_id, self.current_challenge_name

    def set_on_selection_change(self, callback) -> None:
        self._selection_callback = callback

    def _notify_selection_change(self) -> None:
        if hasattr(self, "_selection_callback") and self._selection_callback:
            self._selection_callback()