import asyncio
import logging
from typing import Optional, Callable

from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Static, Button
from textual.screen import ModalScreen
from textual.app import ComposeResult

from ctf_solver.service import ServiceSupervisor, ServiceError
from ctf_solver.ui.textual.widgets.challenges_list import ChallengesList
from ctf_solver.ui.textual.widgets.challenge_runs_panel import ChallengeRunsPanel


class ChallengesView(Horizontal):
    """Main challenges view container combining challenges list and runs panel"""
    
    class RunStarted(Message):
        """Message emitted when a new run is started"""
        def __init__(self, challenge_id: int, attempt_id: str) -> None:
            super().__init__()
            self.challenge_id = challenge_id
            self.attempt_id = attempt_id

    class ConfirmStartRun(ModalScreen[bool]):
        def __init__(self, challenge_name: str, on_result: Callable[[bool], None]) -> None:
            super().__init__()
            self.challenge_name = challenge_name
            self._on_result = on_result

        def compose(self) -> ComposeResult:
            yield Static(
                f"Start a new run for [bold]{self.challenge_name}[/bold]?\n\nRuns can take several minutes.",
                id="confirm-start-body",
            )
            with Horizontal(id="confirm-start-actions"):
                yield Button("Cancel", id="confirm-start-cancel", variant="warning")
                yield Button("Start Run", id="confirm-start-confirm", variant="primary")

        def on_mount(self) -> None:  # type: ignore[override]
            self.app.bell()

        def _confirm(self) -> None:
            self._on_result(True)
            self.dismiss(True)

        def _cancel(self) -> None:
            self._on_result(False)
            self.dismiss(False)

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "confirm-start-confirm":
                self._confirm()
            else:
                self._cancel()

        def key_enter(self) -> None:  # type: ignore[override]
            self._confirm()

        def key_y(self) -> None:  # type: ignore[override]
            self._confirm()

        def key_escape(self) -> None:  # type: ignore[override]
            self._cancel()

        def key_n(self) -> None:  # type: ignore[override]
            self._cancel()

    def compose(self):
        """Compose the challenges view layout"""
        self.challenges_list = ChallengesList()
        self.challenges_list.styles.width = "30%"

        self.runs_panel = ChallengeRunsPanel()
        self.runs_panel.styles.width = "70%"

        # Left side (30%) - challenges list
        yield self.challenges_list

        # Right side (70%) - runs panel
        yield self.runs_panel
        self.runs_panel.set_on_selection_change(self._on_runs_selection_change)

    def _on_runs_selection_change(self) -> None:
        if hasattr(self.app, "update_footer_hint"):
            self.app.update_footer_hint()

    def has_cancelable_selection(self) -> bool:
        return self.runs_panel.get_selected_attempt_status() == "running"

    def selected_run_summary(self) -> tuple[Optional[str], Optional[str]]:
        return (
            self.runs_panel.get_selected_attempt(),
            self.runs_panel.get_selected_attempt_status(),
        )

    async def on_mount(self) -> None:
        """Initialize the view when mounted"""
        self.service = ServiceSupervisor()
        await self.refresh_data()
        # Show helper message about shortcuts
        self.notify("Use s to start a run, c to cancel a running attempt.", severity="information")

    async def refresh_data(self) -> None:
        """Refresh all data in the view"""
        await self.challenges_list.refresh_challenges()

    async def on_challenges_list_challenge_selected(self, event: ChallengesList.ChallengeSelected) -> None:
        """Handle challenge selection - update runs panel"""
        await self.runs_panel.update_challenge(event.challenge_id, event.challenge_name)

    async def _start_run(self, challenge_id: int) -> None:
        logger = logging.getLogger(__name__)

        try:
            attempt_id = await asyncio.to_thread(
                self._ensure_service_then_start, challenge_id
            )
            self.post_message(self.RunStarted(challenge_id, str(attempt_id)))
            if self.runs_panel.current_challenge_id == challenge_id:
                await self.runs_panel.runs_table.refresh_runs_for_challenge(challenge_id)
            self.notify(f"Started run {str(attempt_id)[:8]}…", severity="information")
            logger.info("Started new run %s for challenge %s", attempt_id, challenge_id)
            if hasattr(self.app, "update_status_hint"):
                self.app.update_status_hint()

        except ServiceError as exc:
            logger.error("Service error starting challenge %s: %s", challenge_id, exc)
            self.notify(f"Service error: {exc}", severity="error")
            if hasattr(self.app, "update_status_hint"):
                self.app.update_status_hint()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to start new run for challenge %s: %s", challenge_id, exc)
            self.notify(f"Failed to start run: {exc}", severity="error")
            if hasattr(self.app, "update_status_hint"):
                self.app.update_status_hint()

    def _ensure_service_then_start(self, challenge_id: int) -> int:
        self.service.ensure_running()
        return self.service.start_attempt(challenge_id)

    def action_copy_flag(self) -> None:
        """Copy flag from currently selected run"""
        self.runs_panel.action_copy_flag()

    async def action_refresh(self) -> None:
        """Refresh all data in the view"""
        await self.refresh_data()
        
        # If a challenge is selected, refresh its runs too
        if self.runs_panel.current_challenge_id:
            await self.runs_panel.runs_table.refresh_runs_for_challenge(
                self.runs_panel.current_challenge_id
            )

    def _get_current_challenge_info(self) -> tuple[Optional[int], Optional[str]]:
        return (
            self.challenges_list.current_challenge_id,
            getattr(self.challenges_list, "get_current_challenge_name", lambda: None)(),
        )

    async def action_start_run(self) -> None:
        """Prompt for confirmation before starting a run for the selected challenge."""
        challenge_id, challenge_name = self._get_current_challenge_info()
        if challenge_id is None:
            self.notify("Select a challenge first.", severity="warning")
            return
        def on_result(confirmed: bool) -> None:
            if confirmed:
                asyncio.create_task(self._start_run(challenge_id))

        confirm = self.ConfirmStartRun(challenge_name or "challenge", on_result)
        self.app.push_screen(confirm)

    async def action_cancel_run(self) -> None:
        """Attempt to cancel the selected running attempt."""
        attempt_id = self.runs_panel.get_selected_attempt()
        if not attempt_id:
            self.notify("Select a run in the challenges view first.", severity="warning")
            return
        try:
            cancelled = await asyncio.to_thread(self.service.cancel_attempt, int(attempt_id))
            if cancelled:
                self.notify("Cancellation requested.", severity="information")
            else:
                self.notify("Run was not running anymore.", severity="warning")
        except ServiceError as exc:
            self.notify(f"Service error canceling run: {exc}", severity="error")
        finally:
            if self.runs_panel.current_challenge_id:
                await self.runs_panel.runs_table.refresh_runs_for_challenge(
                    self.runs_panel.current_challenge_id
                )