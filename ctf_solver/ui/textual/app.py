import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.containers import Vertical
from textual import on

from ctf_solver.ui.textual.widgets.jobs_table import JobsTable
from ctf_solver.ui.textual.widgets.log_panel import LogPanel


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
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("y", "copy_flag", "Copy flag"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        self.jobs = JobsTable()
        self.logs = LogPanel()
        yield Vertical(self.jobs, self.logs)
        yield Footer()

    def on_mount(self) -> None:
        # periodic refresh every 2s to reduce CPU
        self.set_interval(2.0, self.refresh_data)
        self.refresh_data()

    def action_copy_flag(self) -> None:
        self.jobs.action_copy_flag()

    async def refresh_data(self) -> None:
        # Run DB work in threads to avoid blocking the UI
        jobs_rows = await asyncio.to_thread(lambda: __import__('ctf_solver.ui.textual.data.repo', fromlist=['fetch_jobs']).fetch_jobs())
        self.jobs.render_jobs(jobs_rows)
        if self.jobs.current_attempt_id:
            logs_rows = await asyncio.to_thread(lambda aid=self.jobs.current_attempt_id: __import__('ctf_solver.ui.textual.data.repo', fromlist=['fetch_logs']).fetch_logs(aid))
            self.logs.render_logs(logs_rows)

    @on(JobsTable.RowSelected)
    async def on_row_selected(self, event: JobsTable.RowSelected) -> None:
        await self.logs.refresh_logs(event.attempt_id)


def run():
    FlaggyTUI().run()


if __name__ == "__main__":
    run()


