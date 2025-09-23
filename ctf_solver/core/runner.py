import re
import time
import json
import logging
from typing import Optional, Dict, Any, List

from ctf_solver.containers.exegol import ExegolContainer
from ctf_solver.agent.dspy_agent import CTFAgent
from ctf_solver.config import EXEGOL_TOOLS, MAX_OUTPUT_TOKENS, MAX_OUTPUT_CHARS, CTF_OUTER_MAX_STEPS
from ctf_solver.core.challenge_manager import ChallengeManager
from ctf_solver.ui.cli_presenter import CLIPresenter


logger = logging.getLogger(__name__)


class ChallengeRunner:
    def __init__(self, db_conn, container_name, use_presenter: bool = True, optimized_agent_name: str = None):
        self.db = db_conn
        self.container_name = container_name
        self.container = None  # Will be initialized with mounts in run_attempt
        self.agent = None  # Will be created fresh for each attempt
        self.optimized_agent_name = optimized_agent_name
        self.challenge_manager = ChallengeManager()
        self.presenter = CLIPresenter() if use_presenter else None
        # Live flag detection during streaming
        self._live_flag = False
        self._live_flag_value: Optional[str] = None
        
        # Suppress verbose logging when using presenter
        if self.presenter:
            self._setup_quiet_logging()
    
    def _setup_quiet_logging(self):
        """Suppress verbose logging when using presenter"""
        # Suppress DSPy agent logging
        logging.getLogger('ctf_solver.agent.dspy_agent').setLevel(logging.WARNING)
        # Suppress container info logging
        logging.getLogger('ctf_solver.containers.exegol').setLevel(logging.WARNING)
        # Suppress challenge manager info
        logging.getLogger('ctf_solver.core.challenge_manager').setLevel(logging.WARNING)
    
    def _encode_output_for_bytea(self, output: str) -> bytes:
        """
        Encode command output as bytes for BYTEA storage.
        
        Args:
            output: Raw command output string
            
        Returns:
            UTF-8 encoded bytes suitable for BYTEA storage
        """
        if not output:
            return b''
        
        try:
            # Truncate very long outputs to prevent database bloat
            max_length = 100000  # 100KB limit
            if len(output) > max_length:
                truncated = output[:max_length] + f"\n\n<TRUNCATED: {len(output) - max_length} more chars>"
                return truncated.encode('utf-8', errors='replace')
            
            return output.encode('utf-8', errors='replace')
            
        except Exception as e:
            # Fallback: if encoding fails, return safe error message as bytes
            logger.warning(f"Failed to encode output: {e}")
            error_msg = f"<ENCODING_ERROR: output length={len(output)}, preview={repr(output[:100])}>"
            return error_msg.encode('utf-8', errors='replace')
    
    @staticmethod
    def decode_bytea_for_training(stored_bytes: bytes) -> str:
        """
        Decode BYTEA storage back to original string for DSPy training.
        
        Args:
            stored_bytes: Bytes from BYTEA column
            
        Returns:
            Original output suitable for LLM training
        """
        if not stored_bytes:
            return ""
        
        try:
            return stored_bytes.decode('utf-8', errors='replace')
        except Exception as e:
            logger.warning(f"Failed to decode BYTEA output: {e}")
            # Return a safe representation
            return f"<DECODE_ERROR: {len(stored_bytes)} bytes>"
    
    def _check_output_size(self, result: Dict[str, Any], command: str) -> Dict[str, Any]:
        """Check if command output is too large and provide guidance to agent"""
        
        stdout = result.get('stdout', '')
        stderr = result.get('stderr', '')
        total_output = stdout + stderr
        
        if len(total_output) > MAX_OUTPUT_CHARS:
            # Replace large output with helpful error message
            guidance_msg = f"""Command output too large ({len(total_output):,} characters, ~{len(total_output)//4:,} tokens).
Maximum allowed: {MAX_OUTPUT_CHARS:,} characters (~{MAX_OUTPUT_TOKENS:,} tokens).

Your command: {command}

Please modify your approach to produce more targeted output. Consider:
- Adding filters (| grep, | head -n 50, | tail -n 50)  
- Searching for specific patterns (| grep -i flag, | grep -E "key|secret")
- Limiting scope (analyzing specific functions/sections instead of full binary)
- Using more targeted tool options
- Breaking analysis into smaller, sequential steps

Try a more specific command that focuses on what you need to find."""

            return {
                'stdout': '',
                'stderr': guidance_msg,
                'exit_code': 1,  # Indicate failure
                'cwd': result.get('cwd', ''),
                'error': 'output_too_large'
            }
        
        return result
        
    def run_attempt(self, challenge_id):
        # Create attempt record first (without container name)
        attempt_id = self._create_attempt(challenge_id)
        
        try:
            # Build container name using attempt_id  
            container_name = f"{self.container_name}_{attempt_id}"
            
            # Update attempt with container name
            self._update_attempt_container(attempt_id, container_name)
            
            # Prepare challenge workspace
            work_dir, container_mounts = self.challenge_manager.prepare_attempt_workspace(
                challenge_id, attempt_id
            )
            
            # Initialize agent (optimized or fresh)
            if self.optimized_agent_name:
                from ctf_solver.optimization import BatchOptimizer
                optimizer = BatchOptimizer()
                self.agent = optimizer.load_optimized_agent(self.optimized_agent_name)
                
                if self.agent is None:
                    logger.warning(f"Failed to load optimized agent '{self.optimized_agent_name}', using fresh agent")
                    self.agent = CTFAgent(container=None)  # Container will be set after creation
                else:
                    logger.info(f"Using optimized agent: {self.optimized_agent_name}")
            else:
                self.agent = CTFAgent(container=None)  # Container will be set after creation
            
            self.container = ExegolContainer(
                container_name,
                mounts=container_mounts
            )
            
            # Update agent with container reference for ReAct tools
            if hasattr(self.agent, 'container'):
                self.agent.container = self.container
            
            # Start container and get available tools
            if not self.container.start():
                raise RuntimeError("Failed to start container")
                
            # Get initial directory listing for LLM context
            ls_result = self.container.execute({'cmd': 'ls -lah'})
            ls_output = ls_result.get('stdout', 'Unable to list directory contents')
            
            # Initialize state
            state = {
                'history': [], 
                'last_output': f'Challenge initialized. Directory contents:\n{ls_output}\nAvailable tool categories: binary_analysis, debugging, exploitation, network, web, crypto, forensics, reverse_engineering, mobile, osint, post_exploitation, utilities. Request tools with action_type="get_tools".',
                'discovered_info': {}
            }
            
            # Get challenge name for display
            cursor = self.db.cursor()
            cursor.execute("SELECT name FROM challenges WHERE id = %s", (challenge_id,))
            result = cursor.fetchone()
            challenge_name = result[0] if result else f"challenge_{challenge_id}"
            
            if self.presenter:
                self.presenter.show_challenge_start(challenge_name, attempt_id)
            else:
                logger.info(f"Starting attempt {attempt_id} for challenge {challenge_id}")
                logger.info(f"Workspace: {work_dir}")
                logger.info("Tools will be requested on-demand to reduce API costs")
                logger.info("Available categories: binary_analysis, debugging, exploitation, network, web, crypto, forensics, reverse_engineering, mobile, osint, post_exploitation, utilities")
            
            for step_num in range(CTF_OUTER_MAX_STEPS):
                # Record execution start time
                start_time = time.time()
                
                try:
                    if not self.presenter:
                        logger.info(f"Step {step_num}: Calling DSPy agent...")
                        logger.debug(f"Current state: {state.keys()}")
                    else:
                        # Start the thinking indicator
                        self.presenter.start_thinking()
                    
                    # Get agent response with reasoning (measure LLM time)
                    llm_start = time.time()
                    agent_response = self.agent(state)
                    llm_duration = time.time() - llm_start
                    
                    # Stop the thinking indicator
                    if self.presenter:
                        self.presenter.stop_thinking()
                    
                    # Handle agent response (CoT-only)
                    if isinstance(agent_response, dict) and 'analysis' in agent_response:
                        # Legacy format: traditional reasoning display
                        analysis = agent_response.get('analysis', '')
                        approach = agent_response.get('approach', '')
                        action_type = agent_response.get('action_type', '')
                        action = agent_response.get('action', {})
                        
                        # Extract command from the action
                        command = action.get('cmd', '') if isinstance(action, dict) else str(action)
                        
                        # Display step with presenter or fallback to logging
                        if self.presenter:
                            self.presenter.show_step(step_num + 1, analysis, approach, action_type, command)
                        else:
                            logger.info(f"Step {step_num}: Agent returned action: {action}")
                            
                    else:
                        # Fallback for unexpected formats
                        analysis = 'Unknown response format'
                        approach = ''
                        action_type = 'unknown'
                        if isinstance(agent_response, dict):
                            action = agent_response
                            command = action.get('cmd', '')
                        else:
                            action = agent_response
                            command = str(agent_response)
                        
                        if self.presenter:
                            self.presenter.show_step(step_num + 1, analysis, approach, action_type, command)
                        else:
                            logger.info(f"Step {step_num}: Fallback - {agent_response}")
                    
                    # Attach reasoning to action for persistence in steps.action JSON
                    try:
                        if isinstance(action, dict):
                            if analysis:
                                action['analysis'] = analysis
                            if approach:
                                action['approach'] = approach
                    except Exception:
                        pass
                        
                except Exception as e:
                    # Make sure to stop thinking indicator on error
                    if self.presenter:
                        self.presenter.stop_thinking()
                        self.presenter.show_error(f"Agent call failed: {e}")
                    else:
                        logger.error(f"Step {step_num}: Agent call failed: {e}")
                    self._mark_failed(attempt_id)
                    return None
                
                # Execute in container for any well-formed action dict (supports bash/read_file/write_file)
                if action and isinstance(action, dict):
                    if not self.presenter:
                        logger.info(f"Step {step_num}: Executing action in container (tool={action.get('tool')})...")
                    shell_start = time.time()
                    result = self.container.execute(action)
                    shell_duration = time.time() - shell_start
                else:
                    result = {'stdout': '', 'stderr': '', 'exit_code': 0, 'tool': action.get('tool') if isinstance(action, dict) else 'bash'}
                    shell_duration = 0.0
                # No extra rendering pass needed (we already showed the analysis/approach step above)
                
                # Check if output is too large and provide guidance if needed
                result = self._check_output_size(result, command)
                
                if not self.presenter:
                    logger.info(f"Step {step_num}: Container execution complete")
                
                # Add execution timing
                if result and 'error' not in result:
                    total_duration = time.time() - start_time
                    result['execution_time_ms'] = int(total_duration * 1000)
                
                self._log_step(attempt_id, step_num, action, result)
                state['history'].append((action, result))
                
                # Update last_output with full stdout+stderr
                stdout = (result or {}).get('stdout', '')
                stderr = (result or {}).get('stderr', '')
                state['last_output'] = stdout + stderr
                
                # Display command output
                if self.presenter:
                    # Get flag format for highlighting
                    cursor = self.db.cursor()
                    cursor.execute("SELECT flag_format FROM challenges WHERE id = %s", (challenge_id,))
                    format_result = cursor.fetchone()
                    flag_format = format_result[0] if format_result else None
                    
                    # Build executed display line for non-bash tools like read_file
                    executed_display = None
                    try:
                        tool_used = (result or {}).get('tool') or (action or {}).get('tool')
                        if tool_used == 'read_file':
                            filename = (action or {}).get('filename', '')
                            max_bytes_val = (action or {}).get('max_bytes')
                            if max_bytes_val is None or max_bytes_val == 0:
                                executed_display = "[bold]read_file[/bold] " + str(filename)
                            else:
                                executed_display = "[bold]read_file[/bold] " + str(filename) + " " + str(max_bytes_val)
                    except Exception:
                        executed_display = None

                    self.presenter.show_command_output(
                        stdout, 
                        stderr, 
                        result.get('exit_code', 0),
                        flag_format,
                        llm_time_s=llm_duration,
                        shell_time_s=shell_duration,
                        total_time_s=total_duration,
                        executed_display=executed_display
                    )
                
                # Update discovered info from results
                self._analyze_result_for_state(state, result)
                
                # Use challenge-specific flag format for detection (stdout or stderr)
                combined_display = (stdout or '') + "\n" + (stderr or '')
                flag = self._extract_flag_from_challenge(challenge_id, combined_display)
                if flag:
                    # Get flag format for display
                    cursor = self.db.cursor()
                    cursor.execute("SELECT flag_format FROM challenges WHERE id = %s", (challenge_id,))
                    format_result = cursor.fetchone()
                    flag_format = format_result[0] if format_result else None
                    
                    if self.presenter:
                        self.presenter.show_flag_found(flag, flag_format)
                    else:
                        logger.info(f"Challenge {challenge_id} solved! Flag: {flag}")
                        
                    self._mark_success(attempt_id, flag, step_num)
                    return flag
                    
            self._mark_failed(attempt_id)
            if self.presenter:
                self.presenter.show_challenge_failed("Maximum steps reached without finding flag")
            else:
                logger.info(f"Challenge {challenge_id} failed after 50 steps")
            return None
            
        except Exception as e:
            logger.error(f"Error in attempt {attempt_id}: {e}")
            self._mark_failed(attempt_id)
            return None
        finally:
            # Clean up container
            if self.container:
                self.container.cleanup()
    
    def _analyze_result_for_state(self, state: Dict[str, Any], result: Dict[str, Any]):
        """Analyze command result and update state with discovered information"""
        if not result or 'stdout' not in result:
            return
            
        stdout = result.get('stdout', '')
        discovered = state['discovered_info']
        
        # Simple pattern detection - let DSPy learn what matters
        if 'ELF 64-bit' in stdout:
            discovered['arch'] = 'x86_64'
        elif 'ELF 32-bit' in stdout:
            discovered['arch'] = 'i386'
            
        if 'NX enabled' in stdout:
            discovered['nx'] = True
        if 'Canary found' in stdout:
            discovered['canary'] = True
        if 'PIE enabled' in stdout:
            discovered['pie'] = True

    def _create_attempt(self, challenge_id: int) -> int:
        """Create a new attempt record in database"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO attempts (challenge_id, status, started_at)
                VALUES (%s, 'running', NOW())
                RETURNING id
            """, (challenge_id,))
            attempt_id = cursor.fetchone()[0]
            self.db.commit()
            logger.info(f"Created attempt {attempt_id} for challenge {challenge_id}")
            return attempt_id
        except Exception as e:
            logger.error(f"Failed to create attempt: {e}")
            self.db.rollback()
            raise
    
    def _update_attempt_container(self, attempt_id: int, container_name: str):
        """Update attempt record with container name"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE attempts SET container_name = %s WHERE id = %s
            """, (container_name, attempt_id))
            self.db.commit()
            logger.debug(f"Updated attempt {attempt_id} with container {container_name}")
        except Exception as e:
            logger.error(f"Failed to update attempt container: {e}")
            self.db.rollback()

    def _log_step(self, attempt_id: int, step_num: int, action: Dict[str, Any], result: Dict[str, Any]):
        """Log a step execution to database"""
        try:
            cursor = self.db.cursor()
            
            # Extract relevant data from result
            output = result.get('stdout', '') + result.get('stderr', '')
            exit_code = result.get('exit_code')
            tool = result.get('tool', action.get('tool', 'bash'))
            
            # Calculate execution time if available
            execution_time = result.get('execution_time_ms')
            
            # Encode output as bytes for BYTEA storage
            output_bytes = self._encode_output_for_bytea(output)
            
            cursor.execute("""
                INSERT INTO steps (attempt_id, step_num, action, output, exit_code, tool, execution_time_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (attempt_id, step_num, json.dumps(action), output_bytes, exit_code, tool, execution_time))
            
            # Update attempt total_steps
            cursor.execute("""
                UPDATE attempts SET total_steps = %s WHERE id = %s
            """, (step_num + 1, attempt_id))
            
            self.db.commit()
            logger.debug(f"Logged step {step_num} for attempt {attempt_id}")
            
        except Exception as e:
            logger.error(f"Failed to log step: {e}")
            self.db.rollback()

    def _extract_flag_from_challenge(self, challenge_id: int, stdout: str) -> Optional[str]:
        """Extract flag using the challenge's specific flag_format from metadata"""
        if not stdout:
            return None
            
        try:
            # Get the flag format from challenge metadata
            cursor = self.db.cursor()
            cursor.execute("SELECT flag_format FROM challenges WHERE id = %s", (challenge_id,))
            result = cursor.fetchone()
            
            if not result:
                # Fallback to standard patterns if no metadata
                flag_format = r'picoCTF\{[^}]+\}'
            else:
                flag_format = result[0]
            
            # Use the challenge's specific flag format
            matches = re.findall(flag_format, stdout, re.IGNORECASE | re.MULTILINE)
            if matches:
                flag = matches[0].strip()
                # Sanity-check to avoid placeholders like %s or template tokens
                try:
                    inner_match = re.search(r"\{([^}]*)\}", flag)
                    inner = inner_match.group(1) if inner_match else ""
                except Exception:
                    inner = ""
                placeholder_like = bool(re.fullmatch(r"\s*%[a-zA-Z]|%\(.*?\)[sd]|\{\w+\}|\s*", inner))
                too_short = len(inner) < 4
                if placeholder_like or too_short:
                    logger.debug(f"Discarding suspicious flag candidate: {flag}")
                else:
                    if self.presenter:
                        logger.info(f"Flag found using format '{flag_format}': {flag}")
                    else:
                        logger.info(f"Flag extracted: {flag}")
                    return flag
                
            # Also check for common flag indicators in output even if format doesn't match
            flag_indicators = [
                r'Flag:\s*([^\s\n]+)',
                r'flag:\s*([^\s\n]+)',
                r'FLAG:\s*([^\s\n]+)',
            ]
            
            for pattern in flag_indicators:
                matches = re.findall(pattern, stdout, re.IGNORECASE | re.MULTILINE)
                if matches:
                    potential_flag = matches[0].strip()
                    # Verify it matches the expected format
                    if re.match(flag_format, potential_flag, re.IGNORECASE):
                        # Apply same sanity check to avoid placeholders
                        try:
                            inner_match = re.search(r"\{([^}]*)\}", potential_flag)
                            inner = inner_match.group(1) if inner_match else ""
                        except Exception:
                            inner = ""
                        placeholder_like = bool(re.fullmatch(r"\s*%[a-zA-Z]|%\(.*?\)[sd]|\{\w+\}|\s*", inner))
                        too_short = len(inner) < 4
                        if not (placeholder_like or too_short):
                            if self.presenter:
                                logger.info(f"Flag found via indicator, verified with format: {potential_flag}")
                            else:
                                logger.info(f"Flag extracted: {potential_flag}")
                            return potential_flag
            
            return None
            
        except Exception as e:
            logger.error(f"Error in flag extraction: {e}")
            return None

    def _extract_flag(self, stdout: str) -> Optional[str]:
        """Extract flag from command output using regex"""
        try:
            # Get flag format for this challenge
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT c.flag_format 
                FROM challenges c 
                JOIN attempts a ON c.id = a.challenge_id 
                WHERE a.id = (SELECT MAX(id) FROM attempts WHERE container_name = %s)
            """, (self.container.container_name,))
            result = cursor.fetchone()
            flag_format = result[0] if result else 'picoCTF{.*}'
            
            # Search for flag pattern
            matches = re.findall(flag_format, stdout, re.IGNORECASE | re.MULTILINE)
            if matches:
                flag = matches[0]
                logger.info(f"Flag extracted: {flag}")
                return flag
            return None
            
        except Exception as e:
            logger.error(f"Error extracting flag: {e}")
            return None

    def _mark_success(self, attempt_id: int, flag: str, step_num: int):
        """Mark attempt as successful with flag"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE attempts 
                SET status = 'completed', flag = %s, total_steps = %s, completed_at = NOW()
                WHERE id = %s
            """, (flag, step_num + 1, attempt_id))
            self.db.commit()
            logger.info(f"Marked attempt {attempt_id} as successful with flag: {flag}")
        except Exception as e:
            logger.error(f"Failed to mark success: {e}")
            self.db.rollback()

    def _get_attempt_data(self, attempt_id: int) -> Dict[str, Any]:
        """Get attempt data from database"""
        try:
            cursor = self.db.cursor()
            
            # Get attempt info
            cursor.execute("""
                SELECT status, flag, total_steps, started_at, completed_at
                FROM attempts WHERE id = %s
            """, (attempt_id,))
            attempt_row = cursor.fetchone()
            
            if not attempt_row:
                return {'success': False, 'steps': []}
            
            status, flag, total_steps, started_at, completed_at = attempt_row
            
            # Get all steps
            cursor.execute("""
                SELECT step_num, action, output, exit_code, tool, created_at
                FROM steps WHERE attempt_id = %s ORDER BY step_num
            """, (attempt_id,))
            steps_rows = cursor.fetchall()
            
            steps = []
            for row in steps_rows:
                step_num, action, output, exit_code, tool, created_at = row
                steps.append({
                    'step_num': step_num,
                    'action': action,
                    'output': output,
                    'exit_code': exit_code,
                    'tool': tool,
                    'timestamp': created_at
                })
            
            return {
                'success': status == 'completed',
                'flag': flag,
                'total_steps': total_steps,
                'started_at': started_at,
                'completed_at': completed_at,
                'steps': steps
            }
            
        except Exception as e:
            logger.error(f"Failed to get attempt data: {e}")
            return {'success': False, 'steps': []}

    def _mark_failed(self, attempt_id: int):
        """Mark attempt as failed"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE attempts 
                SET status = 'failed', completed_at = NOW()
                WHERE id = %s
            """, (attempt_id,))
            self.db.commit()
            logger.info(f"Marked attempt {attempt_id} as failed")
        except Exception as e:
            logger.error(f"Failed to mark failure: {e}")
            self.db.rollback()
            
    def _create_streaming_callback(self, step_num: int, challenge_id: int):
        """Create a streaming callback for real-time ReAct display"""
        # Track current ReAct step being built
        current_react_step = {}
        
        def streaming_callback(event_type: str, data: dict):
            """Handle streaming events from ReAct execution"""
            nonlocal current_react_step
            
            # Capture ReAct execution for context continuity
            react_step_num = data.get('step', 1)
            
            if event_type == 'tool_selection':
                # Start a new ReAct step
                if react_step_num > len(getattr(self, '_current_react_steps', [])):
                    current_react_step = {
                        'step_number': react_step_num,
                        'tool_name': data.get('tool', ''),
                    }
            elif event_type == 'command':
                # Add command details
                if current_react_step.get('step_number') == react_step_num:
                    current_react_step['tool_args'] = data.get('command', '')
            elif event_type == 'tool_result':
                # Complete the ReAct step with result
                if current_react_step.get('step_number') == react_step_num:
                    result_text = data.get('result', '')
                    # Truncate long results
                    if len(result_text) > 400:
                        result_text = result_text[:400] + "..."
                    current_react_step['observation'] = result_text
                    
                    # Store completed step in state for next deliberation
                    if not hasattr(self, '_current_react_steps'):
                        self._current_react_steps = []
                    self._current_react_steps.append(current_react_step.copy())
                    current_react_step = {}
            
            if not self.presenter:
                return
                
            if event_type == 'thought_update':
                # Stop thinking indicator and show live thought
                self.presenter.stop_thinking()
                self.presenter.show_live_thought(
                    step_num, 
                    data.get('step', 1),
                    data.get('thought', ''),
                    data.get('partial', True)
                )
            elif event_type == 'tool_selection':
                # Show tool being selected
                self.presenter.show_live_tool_selection(
                    step_num,
                    data.get('step', 1),
                    data.get('tool', ''),
                    data.get('partial', True)
                )
            elif event_type == 'command':
                # Show command that will be executed
                self.presenter.show_live_command(
                    step_num,
                    data.get('step', 1),
                    data.get('command', '')
                )
            elif event_type == 'tool_result':
                # Show tool execution result
                self.presenter.show_live_tool_result(
                    step_num,
                    data.get('step', 1), 
                    data.get('result', '')
                )
            elif event_type == 'flag_detected':
                # If a live flag is detected, display it and record for early termination
                flag = data.get('flag', '')
                try:
                    cursor = self.db.cursor()
                    cursor.execute("SELECT flag_format FROM challenges WHERE id = %s", (challenge_id,))
                    format_result = cursor.fetchone()
                    flag_format = format_result[0] if format_result else None
                except Exception:
                    flag_format = None
                self.presenter.show_flag_found(flag, flag_format)
                self._live_flag = True
                self._live_flag_value = flag
            elif event_type == 'deliberation':
                # Styled deliberation block before segmented ReAct
                self.presenter.show_deliberation_summary(
                    step_num,
                    data.get('analysis', '') or '',
                    data.get('approach', '') or '',
                    data.get('hypothesis', '') or '',
                    data.get('tests', '') or '',
                    data.get('stop_condition', '') or ''
                )
        
        return streaming_callback


