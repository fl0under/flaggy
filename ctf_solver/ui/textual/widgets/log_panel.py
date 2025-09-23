from typing import List, Tuple

from textual.reactive import reactive
from textual.widgets import RichLog

from ctf_solver.ui.textual.data.repo import fetch_logs


class LogPanel(RichLog):
    content_text: str = reactive("")
    _last_rows_len: int = 0

    def on_mount(self) -> None:  # type: ignore[override]
        # Configure TextLog: wrap lines, show scrollbar, do not auto-scroll on every update
        self.wrap = True
        self.auto_scroll = False

    def render_logs(self, rows: List[Tuple]) -> None:
        # Build text content mirroring Go TUI format
        lines: List[str] = []
        for (
            step_num,
            action,
            output,
            duration_ms,
            analysis,
            approach,
        ) in rows:
            lines.append(f"⚡ Step {step_num}")
            if analysis:
                lines.append("")
                lines.append("🤔 Agent Analysis:")
                lines.append("└── " + str(analysis))
            if approach:
                lines.append("💡 Approach:")
                lines.append("└── " + str(approach))
            lines.append("📤 Output:")
            if not output:
                lines.append("└── <no output>")
            else:
                for line in str(output).split("\n"):
                    if not line:
                        continue
                    lines.append("└── " + line)
            if duration_ms is not None:
                try:
                    secs = float(duration_ms) / 1000.0
                    lines.append(f"⏱️  Step completed in {secs:.1f}s")
                except Exception:
                    lines.append("")
            lines.append("")
        content = "\n".join(lines) if lines else "No logs yet for this attempt"
        # Only update if length changed or content differs (prevents scrollbar jitter)
        if len(rows) == self._last_rows_len and content == self.content_text:
            return
        self.content_text = content
        self.clear()
        if content:
            self.write(content)
        self._last_rows_len = len(rows)

    async def refresh_logs(self, attempt_id: str) -> None:
        rows: List[Tuple] = fetch_logs(attempt_id)
        self.render_logs(rows)


