from typing import Dict, List, Optional, Tuple

from textual.message import Message
from textual.reactive import reactive
from textual.widgets import ListView, ListItem, Label
from textual.containers import Horizontal

from ctf_solver.ui.textual.data.repo import fetch_challenges


class ChallengesList(ListView):
    class ChallengeSelected(Message):
        def __init__(self, challenge_id: int, challenge_name: str) -> None:
            super().__init__()
            self.challenge_id = challenge_id
            self.challenge_name = challenge_name

    current_challenge_id: Optional[int] = reactive(None)
    _index_to_challenge_id: Dict[int, int] = {}
    _last_challenges_signature: List[Tuple] = []

    def on_mount(self) -> None:
        self.border_title = "Challenges"

    def _signature(self, challenges: List[Tuple]) -> List[Tuple]:
        """Create signature for change detection"""
        sig: List[Tuple] = []
        for (challenge_id, name, category, description, total_attempts, latest_status) in challenges:
            sig.append((
                int(challenge_id),
                str(name),
                str(category),
                int(total_attempts),
                str(latest_status or "")
            ))
        return sig

    def render_challenges(self, challenges: List[Tuple]) -> None:
        """Render the challenges list"""
        prev_selected_id = self.current_challenge_id
        prev_index = self.index if self.index is not None else 0

        # No-op if nothing changed
        sig = self._signature(challenges)
        if sig == self._last_challenges_signature:
            return

        # Clear and rebuild
        self.clear()
        self._index_to_challenge_id.clear()

        for idx, (challenge_id, name, category, description, total_attempts, latest_status) in enumerate(challenges):
            # Create status indicator
            status_indicator = ""
            if latest_status == "success":
                status_indicator = "[green]✓[/green]"
            elif latest_status == "failed":
                status_indicator = "[red]✗[/red]"
            elif latest_status == "running":
                status_indicator = "[yellow]▶[/yellow]"

            # Create display text with category and status
            attempts_text = f"({total_attempts})" if total_attempts > 0 else ""
            display_text = f"{status_indicator} {name} [{category}] {attempts_text}"
            
            # Create list item with the challenge info
            list_item = ListItem(Label(display_text))
            self.append(list_item)
            
            # Track mapping from list index to challenge ID
            self._index_to_challenge_id[idx] = int(challenge_id)

        # Restore selection if possible
        target_index = 0
        if prev_selected_id and challenges:
            # Try to find previous selection
            for idx, challenge_id in self._index_to_challenge_id.items():
                if challenge_id == prev_selected_id:
                    target_index = idx
                    break
            else:
                # Fallback to previous index if within bounds
                if prev_index < len(challenges):
                    target_index = prev_index

        # Update selection
        if len(challenges) > 0:
            self.index = target_index
            new_challenge_id = self._index_to_challenge_id.get(target_index)
            if new_challenge_id != self.current_challenge_id:
                self.current_challenge_id = new_challenge_id
                if new_challenge_id:
                    challenge_name = challenges[target_index][1]  # name is at index 1
                    self.post_message(self.ChallengeSelected(new_challenge_id, challenge_name))

        # Update signature
        self._last_challenges_signature = sig

    async def refresh_challenges(self) -> None:
        """Refresh the challenges list from database"""
        challenges: List[Tuple] = fetch_challenges()
        self.render_challenges(challenges)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle challenge selection"""
        if self.index is not None:
            challenge_id = self._index_to_challenge_id.get(self.index)
            if challenge_id and challenge_id != self.current_challenge_id:
                self.current_challenge_id = challenge_id
                # Find challenge name for the message
                challenge_name = "Unknown"
                if hasattr(self, '_last_challenges_signature') and self.index < len(self._last_challenges_signature):
                    challenge_name = self._last_challenges_signature[self.index][1]
                
                self.post_message(self.ChallengeSelected(challenge_id, challenge_name))

    def get_current_challenge_name(self) -> Optional[str]:
        if self.index is not None and 0 <= self.index < len(self._last_challenges_signature):
            return self._last_challenges_signature[self.index][1]
        return None