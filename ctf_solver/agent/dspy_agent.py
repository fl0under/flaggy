import dspy
import logging
from typing import Dict, Any, List
from ctf_solver.config import configure_dspy, EXEGOL_TOOLS

logger = logging.getLogger(__name__)


class CTFAgent(dspy.Module):
    def __init__(self, container=None):
        super().__init__()
        # Configure DSPy in this thread if not already configured
        try:
            if not getattr(dspy.settings, 'lm', None):
                configure_dspy()
        except Exception:
            configure_dspy()
        
        # Store container reference for tool execution
        self.container = container
        
        # Simple CoT-only predictor with structured inputs (idiomatic DSPy)
        cot_signature = dspy.Signature(
            "history_text, info, last_output -> analysis, approach, tool_name, command, filename, content, max_bytes, timeout_seconds",
            (
                "Task: Solve a CTF challenge step-by-step using available tools.\n"
                "Inputs: history_text (recent actions + outputs), info (discovered facts), last_output (latest stdout/stderr).\n"
                "Outputs: analysis and approach, plus exactly ONE action via fields: tool_name in {bash, read_file, write_file},\n"
                "command (bash only), filename (read/write), content (write), max_bytes (read optional), timeout_seconds (bash optional, default 60sec).\n\n"
                "Operating principles: gather context about the challenge first (identify and read artifacts, skim headers/exports/imports etc), determine hypothesis and test them.\n"
                "Tool usage guidelines:\n"
                "- When using read_file, prefer full reads unless size is huge; otherwise limit and iterate.\n"
                "- If a previous read was truncated, re-read without max_bytes.\n"
                "- For bash actions, choose commands that quickly validate hypotheses (e.g., 'file', 'strings -n 6 | head', header dumps, small hexdumps, basic run).\n"
                "- You are executing in a exegol container - a pentesting ditribution, and have access to common pentesting and reverse engineering tools, use them fully.\n"
                "- Output only what is necessary for the next decision."
            )
        )
        self.cot = dspy.ChainOfThought(signature=cot_signature)
        
        # No streaming state needed in CoT-only mode
        
    def forward(self, state):
        # Prepare structured inputs for CoT
        formatted_history = self._format_history(state.get('history', []))
        info_text = self._format_discovered_info(state.get('discovered_info', {}))
        last_output = state.get('last_output', '')
        
        logger.info("=== CoT Inputs ===")
        logger.info(f"History Length: {len(state.get('history', []))} steps")
        logger.info(f"Info Summary: {info_text[:120]}")
        logger.info(f"Last Output: {last_output[:120]}")
        
        # Run CoT predictor with structured fields
        pred = self.cot(history_text=formatted_history, info=info_text, last_output=last_output)
        analysis = getattr(pred, 'analysis', '') or ''
        approach = getattr(pred, 'approach', '') or ''
        tool_name = (getattr(pred, 'tool_name', '') or '').strip().lower()
        command = getattr(pred, 'command', '') or ''
        filename = getattr(pred, 'filename', '') or ''
        content = getattr(pred, 'content', '') or ''
        raw_max_bytes = getattr(pred, 'max_bytes', '') or ''
        raw_timeout_seconds = getattr(pred, 'timeout_seconds', '') or ''
        
        # Parse max_bytes defensively
        try:
            max_bytes = int(raw_max_bytes) if str(raw_max_bytes).strip() else None
        except Exception:
            max_bytes = None
        # Parse timeout_seconds defensively
        try:
            timeout_seconds = int(raw_timeout_seconds) if str(raw_timeout_seconds).strip() else None
        except Exception:
            timeout_seconds = None
        
        # Optional helper to safely single-quote shell strings
        def sh_single_quote(s: str) -> str:
            return "'" + (s or '').replace("'", "'\"'\"'") + "'"
        
        # Map tool_name + fields into runner action
        action: Dict[str, Any]
        if tool_name in ('bash', 'command', 'shell') and command.strip():
            action = {'tool': 'bash', 'cmd': command}
            if isinstance(timeout_seconds, int) and timeout_seconds > 0:
                action['timeout_seconds'] = timeout_seconds
        elif 'read' in tool_name and filename.strip():
            action = {'tool': 'read_file', 'filename': filename}
            if isinstance(max_bytes, int) and max_bytes > 0:
                action['max_bytes'] = max_bytes
        elif 'write' in tool_name and filename.strip():
            action = {'tool': 'write_file', 'filename': filename, 'content': content}
        elif tool_name in ('get_tools', 'get_tools_info', 'tools'):
            category = (filename or command or '').strip()
            try:
                info_text = self.get_tools_info(category)
            except Exception:
                info_text = "Available tool categories: " + ", ".join(EXEGOL_TOOLS.keys())
            action = {'tool': 'bash', 'cmd': f"echo {sh_single_quote(info_text)}"}
        else:
            # Fallback
            action = {'tool': 'bash', 'cmd': 'ls -lah'}
        
        return {
            'analysis': analysis,
            'approach': approach,
            'action_type': action.get('tool', 'bash'),
            'action': action,
        }

    # ===== Container tool helpers =====
    
    def execute_command(self, command: str) -> str:
        """Execute a shell command in the CTF container"""
        if not self.container:
            return "Error: No container available for command execution"
        
        try:
            action = {'tool': 'bash', 'cmd': command}
            result = self.container.execute(action)
            
            stdout = result.get('stdout', '')
            stderr = result.get('stderr', '')
            exit_code = result.get('exit_code', 0)
            
            output_parts = []
            if stdout:
                output_parts.append(f"STDOUT:\n{stdout}")
            if stderr:
                output_parts.append(f"STDERR:\n{stderr}")
            if exit_code != 0:
                output_parts.append(f"EXIT_CODE: {exit_code}")
            
            return "\n".join(output_parts) if output_parts else "Command executed successfully (no output)"
            
        except Exception as e:
            return f"Command execution failed: {e}"

    def read_file(self, filename: str, max_bytes: int = 0) -> str:
        """Read a file inside the CTF container (preferred over sed/cat)."""
        if not self.container:
            return "Error: No container available for file read"
        try:
            action = {
                'tool': 'read_file',
                'filename': filename,
            }
            if isinstance(max_bytes, int) and max_bytes > 0:
                action['max_bytes'] = max_bytes
            result = self.container.execute(action)
            stdout = result.get('stdout', '')
            stderr = result.get('stderr', '')
            if stderr:
                return f"STDERR:\n{stderr}\nSTDOUT:\n{stdout}"
            return stdout if stdout else "(empty file or not found)"
        except Exception as e:
            return f"File read failed: {e}"
    
    def write_file(self, filename: str, content: str) -> str:
        """Write content to a file in the CTF container, avoiding shell escaping issues"""
        if not self.container:
            return "Error: No container available for file writing"
        
        try:
            action = {
                'tool': 'write_file', 
                'filename': filename,
                'content': content
            }
            result = self.container.execute(action)
            
            if result.get('exit_code') == 0:
                return f"Successfully wrote {len(content)} bytes to {filename}"
            else:
                return f"Failed to write {filename}: {result.get('stderr', 'Unknown error')}"
                
        except Exception as e:
            return f"File write failed: {e}"
    
    def get_tools_info(self, category: str = "") -> str:
        """Get information about available CTF tools"""
        if category:
            # Try to match specific category
            category_lower = category.lower()
            for cat, tools in EXEGOL_TOOLS.items():
                if category_lower in cat.lower() or cat.lower() in category_lower:
                    return f"Tools in {cat}: {', '.join(tools)}"
            return f"Category '{category}' not found. Available categories: {', '.join(EXEGOL_TOOLS.keys())}"
        else:
            # Return all categories
            info_lines = []
            for cat, tools in EXEGOL_TOOLS.items():
                info_lines.append(f"{cat}: {len(tools)} tools ({', '.join(tools[:5])}{'...' if len(tools) > 5 else ''})")
            return "Available tool categories:\n" + "\n".join(info_lines)
    
    # ===== Helper Methods =====
    # (Context builder no longer needed; inputs are passed as separate fields)
    
    def _format_history(self, history):
        # History is a list of (action, result)
        lines = []
        for item in history[-10:]:
            try:
                action, result = item
                cmd = action.get('cmd') or action.get('args', {}).get('cmd') or ''
                # Include read_file calls as pseudo-commands for better context
                if not cmd and action.get('tool') == 'read_file':
                    fname = action.get('filename', '')
                    mbytes = action.get('max_bytes')
                    if mbytes:
                        cmd = f"read_file {fname} {mbytes}"
                    else:
                        cmd = f"read_file {fname}"
                # Carry forward reasoning plan when available
                analysis = action.get('analysis') if isinstance(action, dict) else ''
                approach = action.get('approach') if isinstance(action, dict) else ''
                stdout = (result or {}).get('stdout', '')
                stderr = (result or {}).get('stderr', '')
                combined = (stdout or '') + (stderr or '')
                # If result meta indicates truncation, add a concise hint
                try:
                    meta = (result or {}).get('meta') or {}
                    if meta.get('tool') == 'read_file' or action.get('tool') == 'read_file':
                        if meta.get('truncated'):
                            size = meta.get('file_size')
                            readn = meta.get('bytes_returned')
                            hint = f"[Hint] Only {readn} of {size} bytes read; re-read full file."
                            combined = (combined + "\n" + hint).strip()
                except Exception:
                    pass
                if analysis or approach:
                    plan_line = "".join([
                        f"Analysis: {analysis}" if analysis else "",
                        "; " if analysis and approach else "",
                        f"Approach: {approach}" if approach else "",
                    ])
                    lines.append(f"$ {cmd}\n{plan_line}\n{combined}")
                else:
                    lines.append(f"$ {cmd}\n{combined}")
            except Exception:
                continue
        return "\n\n".join(lines)

    def _format_discovered_info(self, discovered_info: dict) -> str:
        """Format discovered information for LLM context"""
        if not discovered_info:
            return "No analysis completed yet"
            
        info_lines = []
        for key, value in discovered_info.items():
            info_lines.append(f"{key.replace('_', ' ').title()}: {value}")
            
        return ", ".join(info_lines) if info_lines else "No information discovered"