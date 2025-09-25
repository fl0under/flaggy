import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static
from textual.containers import Vertical
from textual import on
from textual.reactive import reactive

from ctf_solver.service import ServiceSupervisor, ServiceError
from ctf_solver.ui.textual.widgets.jobs_table import JobsTable
from ctf_solver.ui.textual.widgets.log_panel import LogPanel
from ctf_solver.ui.textual.widgets.challenges_view import ChallengesView


class FlaggyTUI(App):
    CSS = """
    Vertical {
        height: 1fr;
    }
    # Jobs table top third, logs bottom part
    Vertical > *:first-child {
        height: 33%;
        min-height: 8;
    }
    Vertical > *:last-child {
        height: 1fr;
    }
    
    # Challenges view specific styling
    ChallengesView {
        height: 1fr;
    }
    ChallengesList {
        width: 30%;
        min-width: 20;
    }
    ChallengeRunsPanel {
        width: 70%;
    }
    
    # Runs table and log panel in challenges view
    RunsTable {
        height: 40%;
        min-height: 8;
    }
    LogPanel {
        height: 60%;
    }
    # Status bar text
    #status-bar {
        height: auto;
        padding: 0 1;
        color: $text;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("y", "copy_flag", "Copy flag"),
        ("m", "toggle_mode", "Toggle mode"),
        ("r", "refresh", "Refresh"),
        ("s", "start_run", "Start run"),
        ("c", "cancel_run", "Cancel run"),
    ]

    # Current mode: "jobs" or "challenges"
    current_mode: str = reactive("jobs")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        
        # Create both views - we'll show/hide them instead of recomposing
        self.jobs = JobsTable()
        self.logs = LogPanel()
        self.jobs_view = Vertical(self.jobs, self.logs)
        self.challenges_view = ChallengesView()
        
        # Add both views but initially hide challenges view
        yield self.jobs_view
        yield self.challenges_view
        
        self.footer = Footer()
        yield self.footer
        self.status = Static(id="status-bar")
        yield self.status

    def on_mount(self) -> None:
        # periodic refresh every 2s to reduce CPU
        self.service = ServiceSupervisor()
        self.set_interval(2.0, self.refresh_data)
        self.refresh_data()
        self.update_title()
        self.update_view_visibility()
        self.update_status_hint()

    def update_title(self) -> None:
        """Update header title based on current mode"""
        mode_name = "Jobs" if self.current_mode == "jobs" else "Challenges"
        self.title = f"Flaggy TUI - {mode_name} Mode"

    def update_view_visibility(self) -> None:
        """Show/hide views based on current mode"""
        if self.current_mode == "jobs":
            self.jobs_view.display = True
            self.challenges_view.display = False
            self.call_later(lambda: self.set_focus(self.jobs))
        else:
            self.jobs_view.display = False
            self.challenges_view.display = True
            self.call_later(lambda: self.set_focus(self.challenges_view.challenges_list))
        self.update_status_hint()

    def update_status_hint(self) -> None:
        if not hasattr(self, "status"):
            return
        if self.current_mode != "challenges":
            hint = "m: switch to Challenges. In Challenges use s to start and c to cancel runs."
        else:
            _, status = self.challenges_view.selected_run_summary()
            if status == "running":
                hint = "s: start new run. c: cancel selected running attempt (focus on Runs table)."
            else:
                hint = "s: start run for selected challenge (focus on Challenges list). c: needs a running attempt selected in Runs table."
        self.status.update(hint)

    def action_copy_flag(self) -> None:
        """Copy flag from current view"""
        if self.current_mode == "jobs":
            self.jobs.action_copy_flag()
        else:
            self.challenges_view.action_copy_flag()

    async def action_toggle_mode(self) -> None:
        """Toggle between jobs and challenges modes"""
        # Switch mode
        self.current_mode = "challenges" if self.current_mode == "jobs" else "jobs"
        self.update_title()
        self.update_view_visibility()
        self.update_status_hint()
        
        # Refresh data for new mode (non-blocking)
        self.call_later(self.refresh_data)

    async def action_refresh(self) -> None:
        """Manually refresh current view"""
        await self.refresh_data()

    async def action_start_run(self) -> None:
        """Start a new run for selected challenge (challenges mode only)"""
        if self.current_mode == "challenges":
            await self.challenges_view.action_start_run()
            self.update_status_hint()

    async def action_cancel_run(self) -> None:
        """Cancel run shortcut passes through to challenges view."""
        if self.current_mode == "challenges":
            await self.challenges_view.action_cancel_run()
            self.update_status_hint()
        else:
            self.notify("Switch to challenges mode to cancel runs.", severity="warning")

    async def refresh_data(self) -> None:
        """Refresh data based on current mode"""
        if self.current_mode == "jobs":
            # Run DB work in threads to avoid blocking the UI
            jobs_rows = await asyncio.to_thread(lambda: __import__('ctf_solver.ui.textual.data.repo', fromlist=['fetch_jobs']).fetch_jobs())
            self.jobs.render_jobs(jobs_rows)
            if self.jobs.current_attempt_id:
                logs_rows = await asyncio.to_thread(lambda aid=self.jobs.current_attempt_id: __import__('ctf_solver.ui.textual.data.repo', fromlist=['fetch_logs']).fetch_logs(aid))
                self.logs.render_logs(logs_rows)
        else:
            # Refresh challenges view
            await self.challenges_view.refresh_data()
        self.update_status_hint()

    @on(JobsTable.RowSelected)
    async def on_row_selected(self, event: JobsTable.RowSelected) -> None:
        if self.current_mode == "jobs":
            await self.logs.refresh_logs(event.attempt_id)


def run() -> None:
    FlaggyTUI().run()


if __name__ == "__main__":
    run()