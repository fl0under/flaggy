"""
Beautiful CLI presentation for flaggy
"""
import time
import random
import threading
from typing import Dict, Any, Optional
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.syntax import Syntax
from rich.text import Text
from rich.tree import Tree
from rich.columns import Columns
from rich.live import Live
import re

console = Console()

class CLIPresenter:
    def __init__(self):
        self.current_step = 0
        self.max_steps = 50
        self.start_time = time.time()
        self.step_start_time = time.time()
        self.thinking_active = False
        self.thinking_thread = None
        
        # Hacker-themed thinking messages (no emojis, clearer intent)
        self.thinking_messages = [
            "hacking the mainframe",
            "cracking the code", 
            "analyzing the binary",
            "searching for vulnerabilities",
            "decoding the challenge",
            "hunting for flags",
            "breaking into the system",
            "exploiting weaknesses",
            "reverse engineering",
            "pwning the target",
            "infiltrating defenses",
            "bypassing security",
            "escalating privileges", 
            "rooting the box",
            "compromising the server",
            "gaining access",
            "executing payload",
            "owning the system",
        ]
        
        # Hex/binary animation frames
        self.hex_frames = [
            "0x41", "0x42", "0x43", "0x44", "0x45", "0x46", 
            "0x47", "0x48", "0x49", "0x4A", "0x4B", "0x4C"
        ]
        
        self.binary_frames = [
            "0001", "0010", "0100", "1000", "0100", "0010"
        ]
        
    def show_challenge_start(self, challenge_name: str, attempt_id: int):
        """Display challenge start banner"""
        banner = Panel.fit(
            f"🎯 [bold blue]Challenge:[/bold blue] {challenge_name}\n"
            f"🔄 [dim]Attempt ID:[/dim] {attempt_id}",
            border_style="blue",
            padding=(1, 2)
        )
        console.print(banner)
        console.print()
    
    def start_thinking(self):
        """Start the thinking indicator animation"""
        self.thinking_active = True
        self.thinking_thread = threading.Thread(target=self._thinking_animation)
        self.thinking_thread.daemon = True
        self.thinking_thread.start()
    
    def stop_thinking(self):
        """Stop the thinking indicator"""
        self.thinking_active = False
        if self.thinking_thread:
            self.thinking_thread.join(timeout=1.0)
    
    def _thinking_animation(self):
        """Animated thinking indicator with random hex/binary animation"""
        message_index = 0
        frame_count = 0
        use_hex = random.choice([True, False])  # Random start
        last_message_change = time.time()
        message_interval_s = 4.0  # show each message for 4 seconds
        
        with Live(refresh_per_second=3, console=console, transient=True) as live:
            while self.thinking_active:
                # Deterministic message change every message_interval_s seconds
                now = time.time()
                if frame_count == 0 or (now - last_message_change) >= message_interval_s:
                    message_index = (message_index + 1) % len(self.thinking_messages)
                    last_message_change = now
                
                message = self.thinking_messages[message_index]
                
                # Generate random animation frames instead of cycling
                if use_hex:
                    # Random hex values
                    hex_val = random.randint(0x40, 0x7F)  # Printable ASCII range
                    animation_frame = f"0x{hex_val:02X}"
                    animation_style = "bold green"
                else:
                    # Random binary patterns
                    binary_val = random.randint(0, 15)  # 4-bit values
                    animation_frame = f"{binary_val:04b}"
                    animation_style = "bold cyan"
                
                thinking_text = Text()
                thinking_text.append(f"[{animation_frame}] ", style=animation_style)
                thinking_text.append(message, style="dim white")
                thinking_text.append("...", style="dim")
                
                live.update(thinking_text)
                
                time.sleep(0.33)  # Keep same timing
                frame_count += 1
                
                # Randomly switch between hex and binary
                if random.random() < 0.08:  # ~8% chance to switch type
                    use_hex = not use_hex
        
    def show_step(self, step_num: int, analysis: str, approach: str, action_type: str, command: str):
        """Display a formatted step with agent reasoning and action"""
        self.current_step = step_num
        self.step_start_time = time.time()
        
        # Step header with progress
        progress_text = f"Step {step_num}/{self.max_steps}"
        elapsed = int(time.time() - self.start_time)
        elapsed_text = f"{elapsed}s elapsed"
        
        header = Text()
        header.append("⚡ ", style="bold yellow")
        header.append(progress_text, style="bold white")
        header.append(f" • {elapsed_text}", style="dim white")
        
        console.print(header)
        console.print()
        
        # Create tree structure for the step
        step_tree = Tree("", hide_root=True)
        
        # Agent Analysis
        if analysis.strip():
            analysis_node = step_tree.add("🤔 [bold cyan]Agent Analysis:[/bold cyan]")
            # Wrap long analysis text
            wrapped_analysis = self._wrap_text(analysis, width=80)
            analysis_node.add(Text(wrapped_analysis, style="cyan"))
        
        # Approach
        if approach.strip():
            approach_node = step_tree.add("💡 [bold blue]Approach:[/bold blue]")
            wrapped_approach = self._wrap_text(approach, width=80)
            approach_node.add(Text(wrapped_approach, style="blue"))
        
        # Command
        command_node = step_tree.add("⚡ [bold yellow]Command:[/bold yellow]")
        
        # Format command nicely
        if command.strip().startswith('$'):
            # Remove leading $ if present
            clean_command = command.strip()[1:].strip()
        else:
            clean_command = command.strip()
            
        # Syntax highlight the command
        if clean_command:
            try:
                syntax = Syntax(clean_command, "bash", theme="monokai", line_numbers=False, padding=(0, 1))
                command_node.add(syntax)
            except:
                # Fallback if syntax highlighting fails
                command_node.add(Text(f"$ {clean_command}", style="yellow"))
        
        console.print(step_tree)
        console.print()
        
    def show_command_output(self, output: str, stderr: str = "", exit_code: int = 0, flag_format: str = None, *, llm_time_s: float = None, shell_time_s: float = None, total_time_s: float = None, executed_display: Optional[str] = None):
        """Display command output in a formatted way, with optional timing breakdown."""
        output_tree = Tree("", hide_root=True)
        
        # Show executed tool/command for non-bash tools (e.g., read_file)
        if executed_display:
            exec_node = output_tree.add("⚙️  [bold yellow]Executed:[/bold yellow]")
            try:
                exec_text = Text.from_markup(executed_display)
            except Exception:
                exec_text = Text(executed_display)
            exec_node.add(exec_text)
        
        # Determine output style based on exit code
        if exit_code == 0:
            output_node = output_tree.add("📤 [bold green]Output:[/bold green]")
            output_style = "white"
        else:
            output_node = output_tree.add("❌ [bold red]Output (Error):[/bold red]")
            output_style = "red"
            
        # Clean and format output
        if output and output.strip():
            clean_output = output.strip()
            
            # Highlight actual flags using challenge-specific format
            if flag_format and self._contains_flag_with_format(clean_output, flag_format):
                flag_text = Text(clean_output)
                self._highlight_flags_with_format(flag_text, flag_format)
                output_node.add(flag_text)
            else:
                # Truncate very long output
                if len(clean_output) > 2000:
                    truncated = clean_output[:2000] + "\n... (output truncated)"
                    output_node.add(Text(truncated, style=output_style))
                else:
                    output_node.add(Text(clean_output, style=output_style))
        else:
            output_node.add(Text("(no output)", style="dim"))
            
        # Show stderr if present
        if stderr and stderr.strip():
            stderr_node = output_tree.add("⚠️  [bold yellow]Stderr:[/bold yellow]")
            stderr_node.add(Text(stderr.strip(), style="yellow"))
            
        console.print(output_tree)
        
        # Show step timing
        if total_time_s is not None:
            parts = [f"⏱️  Step completed in {total_time_s:.1f}s"]
            if llm_time_s is not None:
                parts.append(f"[LLM {llm_time_s:.1f}s]")
            if shell_time_s is not None:
                parts.append(f"[Shell {shell_time_s:.1f}s]")
            console.print("[dim]" + " ".join(parts) + "[/dim]")
        else:
            step_elapsed = time.time() - self.step_start_time
            console.print(f"[dim]⏱️  Step completed in {step_elapsed:.1f}s[/dim]")
        console.print()
        
    def show_flag_found(self, flag: str, flag_format: str = None):
        """Display flag found celebration"""
        content = f"🎉 [bold green]FLAG FOUND![/bold green]\n\n[bold white]{flag}[/bold white]\n\n"
        
        if flag_format:
            content += f"[dim]Format: {flag_format}[/dim]\n\n"
            
        content += f"[green]Challenge completed successfully! 🏆[/green]"
        
        flag_panel = Panel.fit(
            content,
            border_style="green",
            padding=(1, 2),
            title="🏁 SUCCESS",
            title_align="center"
        )
        console.print(flag_panel)
        
        # Show total time
        total_elapsed = int(time.time() - self.start_time)
        console.print(f"[bold green]✅ Total time: {total_elapsed}s • Steps: {self.current_step}/{self.max_steps}[/bold green]")
        console.print()
        
    def show_challenge_failed(self, reason: str = "Max steps reached"):
        """Display challenge failure"""
        failure_panel = Panel.fit(
            f"❌ [bold red]Challenge Failed[/bold red]\n\n"
            f"[white]{reason}[/white]\n\n"
            f"[dim]Completed {self.current_step}/{self.max_steps} steps[/dim]",
            border_style="red",
            padding=(1, 2),
            title="💥 FAILED",
            title_align="center"
        )
        console.print(failure_panel)
        
        total_elapsed = int(time.time() - self.start_time)
        console.print(f"[bold red]❌ Total time: {total_elapsed}s[/bold red]")
        console.print()
        
    def show_error(self, error: str):
        """Display error message"""
        error_panel = Panel(
            f"[bold red]Error:[/bold red] {error}",
            border_style="red",
            padding=(1, 2)
        )
        console.print(error_panel)
        console.print()
        
    def _wrap_text(self, text: str, width: int = 80) -> str:
        """Simple text wrapping"""
        import textwrap
        return textwrap.fill(text, width=width)
        
    def _contains_flag_with_format(self, text: str, flag_format: str) -> bool:
        """Check if text contains flags matching the specific challenge format"""
        try:
            return bool(re.search(flag_format, text, re.IGNORECASE))
        except:
            return False
        
    def _highlight_flags_with_format(self, text: Text, flag_format: str):
        """Highlight flags that match the challenge-specific format"""
        try:
            content = str(text)
            matches = re.finditer(f'({flag_format})', content, re.IGNORECASE)
            for match in matches:
                start, end = match.span(1)
                text.stylize("bold green on black", start, end)
        except:
            # If regex fails, don't highlight anything
            pass
            
    def _contains_flag(self, text: str) -> bool:
        """Check if text contains actual flag formats (only with curly braces) - fallback method"""
        flag_patterns = [
            r'picoCTF\{[^}]+\}',
            r'flag\{[^}]+\}',
            r'FLAG\{[^}]+\}',
        ]
        
        for pattern in flag_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
        
    def _highlight_flags(self, text: Text):
        """Highlight actual flags (only proper format with curly braces) - fallback method"""
        flag_patterns = [
            (r'(picoCTF\{[^}]+\})', "bold green on black"),
            (r'(flag\{[^}]+\})', "bold green on black"),
            (r'(FLAG\{[^}]+\})', "bold green on black"),
        ]
        
        content = str(text)
        for pattern, style in flag_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                start, end = match.span(1)
                text.stylize(style, start, end)

    def show_react_trajectory(self, step_num: int, trajectory: list):
        """Display ReAct reasoning trajectory step-by-step like Cursor/Claude"""
        self.current_step = step_num
        self.step_start_time = time.time()
        
        # Step header with progress
        progress_text = f"Step {step_num}/{self.max_steps}"
        elapsed = int(time.time() - self.start_time)
        elapsed_text = f"{elapsed}s elapsed"
        
        header = Text()
        header.append("⚡ ", style="bold yellow")
        header.append(progress_text, style="bold white")
        header.append(f" • {elapsed_text}", style="dim white")
        
        console.print(header)
        console.print()
        
        # Create tree structure for the trajectory
        react_tree = Tree("🤖 [bold green]ReAct Reasoning Process:[/bold green]", hide_root=False)
        
        for i, step in enumerate(trajectory):
            step_node = react_tree.add(f"[bold white]Reasoning Step {step.get('step_number', i+1)}[/bold white]")
            
            # Show thought process
            if step.get('thought'):
                thought_text = step['thought'].strip()
                if len(thought_text) > 100:
                    thought_text = thought_text[:97] + "..."
                step_node.add(f"🤔 [cyan]Thought:[/cyan] {thought_text}")
            
            # Show tool call
            if step.get('tool_name'):
                tool_name = step['tool_name']
                tool_args = step.get('tool_args', '')
                
                # Format tool arguments nicely
                if isinstance(tool_args, dict):
                    args_display = ", ".join([f"{k}={v}" for k, v in tool_args.items()])
                elif isinstance(tool_args, str):
                    args_display = tool_args[:50] + "..." if len(tool_args) > 50 else tool_args
                else:
                    args_display = str(tool_args)
                
                step_node.add(f"🔧 [yellow]Tool Call:[/yellow] {tool_name}({args_display})")
            
            # Show observation/result
            if step.get('observation'):
                obs_text = step['observation'].strip()
                if len(obs_text) > 150:
                    obs_text = obs_text[:147] + "..."
                step_node.add(f"📄 [green]Result:[/green] {obs_text}")
        
        # Display the trajectory tree
        console.print(react_tree)
        console.print()
        
        # Show summary only if there were actual reasoning steps
        if trajectory:
            summary = Text()
            summary.append("✨ ", style="bold green")
            summary.append(f"Completed {len(trajectory)} reasoning steps", style="bold white")
            console.print(summary)
            console.print()
        console.print("─" * 80, style="dim")
        console.print()

    def show_deliberation_summary(self, step_num: int, analysis: str, approach: str, hypothesis: str = "", tests: str = "", stop_condition: str = ""):
        """Styled deliberation display similar to old Agent Analysis/Approach."""
        self.current_step = step_num
        self.step_start_time = time.time()

        header = Text()
        header.append("🧠 ", style="bold magenta")
        header.append(f"Deliberation for Step {step_num}", style="bold magenta")
        console.print(header)
        console.print()

        tree = Tree("", hide_root=True)

        if analysis.strip():
            analysis_node = tree.add("🤔 [bold cyan]Agent Analysis:[/bold cyan]")
            analysis_node.add(Text(self._wrap_text(analysis, width=80), style="cyan"))

        if approach.strip():
            approach_node = tree.add("💡 [bold blue]Approach:[/bold blue]")
            approach_node.add(Text(self._wrap_text(approach, width=80), style="blue"))

        if hypothesis.strip():
            hyp_node = tree.add("📌 [bold magenta]Hypothesis:[/bold magenta]")
            hyp_node.add(Text(self._wrap_text(hypothesis, width=80), style="magenta"))

        if tests.strip():
            tests_node = tree.add("🧪 [bold green]Tests:[/bold green]")
            tests_node.add(Text(self._wrap_text(tests, width=80), style="green"))

        if stop_condition.strip():
            stop_node = tree.add("⛔ [bold yellow]Stop Condition:[/bold yellow]")
            stop_node.add(Text(self._wrap_text(stop_condition, width=80), style="yellow"))

        console.print(tree)
        console.print()
    
    def show_live_thought(self, step_num: int, reasoning_step: int, thought: str, partial: bool = True):
        """Show live streaming thought as it's being generated"""
        # Create live display of the thought with proper styling (no markup tags)
        thought_text = thought.strip()
        # Do not truncate the thought; show full content
        
        live_text = Text()
        live_text.append(f"Step {step_num}.{reasoning_step} • ", style="dim")
        if partial:
            live_text.append("🤔 ", style="white")
            live_text.append("thinking...", style="italic dim")
        else:
            live_text.append("🤔 ", style="white")
            live_text.append("Thought complete", style="cyan")
        live_text.append(":\n", style="white")
        live_text.append(thought_text, style="white")
        
        console.print(live_text)
        
    def show_live_tool_selection(self, step_num: int, reasoning_step: int, tool_name: str, partial: bool = True):
        """Show tool selection as it's happening"""
        live_text = Text()
        live_text.append(f"Step {step_num}.{reasoning_step} • ", style="dim")
        live_text.append("🔧 ", style="yellow")
        if partial:
            live_text.append("selecting...", style="italic dim")
        else:
            live_text.append("Tool selected", style="yellow")
        live_text.append(": ", style="yellow")
        live_text.append(str(tool_name), style="yellow")
        console.print(live_text)
    
    def show_live_tool_result(self, step_num: int, reasoning_step: int, result: str):
        """Show tool execution result"""
        result_text = result.strip()
        # Increase preview budget so flags like "Correct password! Flag: ..." are visible
        preview_limit = 400
        if len(result_text) > preview_limit:
            truncated = result_text[:preview_limit] + "\n... (output truncated)"
            result_text = truncated
            
        live_text = Text()
        live_text.append(f"Step {step_num}.{reasoning_step} • ", style="dim") 
        live_text.append("📄 ", style="green")
        live_text.append("Result", style="green")
        live_text.append(":\n", style="white")
        live_text.append(result_text, style="white")
        
        console.print(live_text)

    def show_live_command(self, step_num: int, reasoning_step: int, command: str):
        """Show the exact command that will be executed next."""
        live_text = Text()
        live_text.append(f"Step {step_num}.{reasoning_step} • ", style="dim")
        live_text.append("⚡ ", style="yellow")
        live_text.append("Command", style="bold yellow")
        live_text.append(": ", style="yellow")
        # Syntax highlight
        try:
            syntax = Syntax(command, "bash", theme="monokai", line_numbers=False, padding=(0, 1))
            console.print(live_text)
            console.print(syntax)
        except Exception:
            live_text.append(command, style="yellow")
            console.print(live_text)