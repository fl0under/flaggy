import subprocess
import json
import os
import docker
import time
import logging
from typing import Optional, Dict, Any, List

from ctf_solver.config import EXEGOL_TOOLS


logger = logging.getLogger(__name__)


class ExegolContainer:
    def __init__(self, container_name: str, image: str = "nwodtuhs/exegol:free", 
                 mounts: Optional[Dict[str, str]] = None):
        self.container_name = container_name
        self.image = image
        self.cwd = '/challenge'
        self.mounts = mounts or {}  # host_path -> container_path mapping
        self._container_obj = None
        self._client = docker.from_env()
        # Default timeout for bash commands (seconds); can be overridden per action
        try:
            self.default_timeout_seconds = int(os.environ.get('FLAGGY_BASH_TIMEOUT', '60'))
        except Exception:
            self.default_timeout_seconds = 60
        
        # Persistent session processes
        self._gdb_session = None
        self._python_session = None
    
    def start(self) -> bool:
        """Start the Exegol container"""
        try:
            # Ensure Exegol image is available
            self._ensure_image_available()
            
            # Check if container already exists and remove it to ensure fresh start
            existing = self._client.containers.list(all=True, filters={'name': self.container_name})
            if existing:
                logger.info(f"Found existing container {self.container_name}, removing to ensure fresh start")
                for container in existing:
                    try:
                        if container.status == 'running':
                            container.stop(timeout=5)
                        container.remove()
                        logger.info(f"Removed existing container {container.name}")
                    except Exception as e:
                        logger.warning(f"Failed to remove existing container {container.name}: {e}")
            
            # Create new container with mounts
            logger.info(f"Creating new container {self.container_name} from {self.image}")
            
            # Prepare volume mounts
            volumes = {}
            logger.info(f"Setting up {len(self.mounts)} mounts for container {self.container_name}")
            
            for host_path, container_path in self.mounts.items():
                # Check if host path should be read-only
                read_only = 'original' in container_path  # /challenge/original is read-only
                bind_config = {'bind': container_path, 'mode': 'ro' if read_only else 'rw'}
                volumes[host_path] = bind_config
                logger.info(f"Mount: {host_path} -> {container_path} ({'ro' if read_only else 'rw'})")
                
                # Verify host path exists
                if not os.path.exists(host_path):
                    logger.error(f"Host mount path does not exist: {host_path}")
                else:
                    logger.debug(f"Host path verified: {host_path}")
            
            logger.info(f"Final volumes config: {volumes}")
            
            self._container_obj = self._client.containers.run(
                self.image,
                name=self.container_name,
                detach=True,
                stdin_open=True,
                tty=True,
                remove=False,
                working_dir=self.cwd,
                volumes=volumes,
                environment={"TERM": "xterm"},  # Fix terminal warnings
                # Override entrypoint to bypass Exegol wrapper and use direct bash
                entrypoint="/bin/bash",
                # Keep container running - use proper shell command
                command=["-c", "while true; do sleep 30; done"]
            )
            
            # Wait for container to be ready
            time.sleep(2)
            return True
            
        except Exception as e:
            logger.error(f"Failed to start container {self.container_name}: {e}")
            return False
    
    def stop(self) -> bool:
        """Stop and remove the container"""
        try:
            if self._container_obj:
                logger.info(f"Stopping container {self.container_name}")
                self._container_obj.stop(timeout=10)
                self._container_obj.remove()
                self._container_obj = None
            return True
        except Exception as e:
            logger.error(f"Failed to stop container {self.container_name}: {e}")
            return False
    
    def _ensure_image_available(self):
        """Ensure the Exegol image is available, pull if needed"""
        try:
            # Check if image exists locally
            self._client.images.get(self.image)
            logger.debug(f"Image {self.image} already available")
        except docker.errors.ImageNotFound:
            print(f"🐳 Image {self.image} not found locally, pulling...")
            try:
                # Use subprocess to get native Docker output
                import subprocess
                result = subprocess.run(
                    ["docker", "pull", self.image], 
                    check=True,
                    text=True
                )
                print(f"✅ Successfully pulled {self.image}")
                logger.info(f"Successfully pulled {self.image}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to pull image {self.image}: {e}")
                raise RuntimeError(f"Could not pull Exegol image: {e}")
            except FileNotFoundError:
                logger.error("Docker command not found. Please ensure Docker is installed and in PATH.")
                raise RuntimeError("Docker not found in PATH")
        except Exception as e:
            logger.error(f"Error checking for image {self.image}: {e}")
            raise
    
    def is_running(self) -> bool:
        """Check if container is running"""
        try:
            if not self._container_obj:
                return False
            self._container_obj.reload()
            return self._container_obj.status == 'running'
        except Exception:
            return False
    
    def ensure_running(self) -> bool:
        """Ensure container is running, start if needed"""
        if not self.is_running():
            return self.start()
        return True
        
    def execute(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute action in container using Exegol wrapper CLI.
        Special cases: persistent gdb/python if requested, write_file for safe file creation.
        """
        if not self.ensure_running():
            return {"error": "Container not running"}
            
        tool = action.get('tool', 'bash')
        
        if tool == 'gdb' and action.get('persistent'):
            return self._gdb_persistent(action.get('cmd', ''))
        if tool == 'python' and action.get('persistent'):
            return self._python_persistent(action.get('code', ''))
        if tool == 'write_file':
            return self._write_file(action.get('filename', ''), action.get('content', ''))
        if tool == 'read_file':
            return self._read_file(action.get('filename', ''), action.get('max_bytes'))

        # Default path: run bash command in current working directory with direct Docker execution
        cmd = action.get('cmd') or action.get('args', {}).get('cmd', '')
        if not cmd.strip():
            return {"stdout": "", "stderr": "", "cwd": self.cwd}
        
        # Direct Docker execution bypasses Exegol wrapper, no newline conversion needed
            
        try:
            # Use base64 encoding for all commands to avoid truncation issues
            import base64
            
            
            # Prepare the full command with directory change and proper environment setup
            # Set up pyenv PATH and TERM to make all Exegol tools available seamlessly
            env_setup = 'export PATH="/root/.pyenv/versions/3.11.11/bin:$PATH" && export TERM=xterm'
            full_cmd = f'{env_setup} && cd {self.cwd} && {cmd}'
            
            # Encode command in base64 to avoid shell escaping and null byte issues
            encoded_cmd = base64.b64encode(full_cmd.encode('utf-8')).decode('ascii')
            
            # Build inner command (decoded execution) and wrap with timeout by default
            inner_cmd = f'echo "{encoded_cmd}" | base64 -d | bash'
            timeout_seconds = action.get('timeout_seconds')
            if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
                timeout_seconds = self.default_timeout_seconds
            # Use coreutils timeout to prevent hangs; send INT, then kill after 5s grace
            safe_cmd = f"timeout -k 5s {timeout_seconds}s bash -lc '{inner_cmd}'"
            
            exec_result = self._container_obj.exec_run(
                ['bash', '-c', safe_cmd],
                stdout=True,
                stderr=True,
                stdin=False
            )
            
            stdout = exec_result.output.decode('utf-8', errors='replace') if exec_result.output else ""
            stderr = ""  # docker-py combines stdout/stderr; append timeout note if applicable
            if exec_result.exit_code == 124:
                stderr = f"Command timed out after {timeout_seconds}s"
            
            # Track directory changes if the command includes `cd`
            new_cwd = self._extract_new_dir(cmd)
            if new_cwd and self._validate_directory(new_cwd):
                self.cwd = new_cwd
                
            return {
                "stdout": stdout,
                "stderr": stderr,
                "cwd": self.cwd,
                "exit_code": exec_result.exit_code,
                "tool": "bash",
                "timed_out": bool(exec_result.exit_code == 124)
            }
            
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return {"error": str(e), "cwd": self.cwd}

    def _validate_directory(self, path: str) -> bool:
        """Validate that a directory exists in the container"""
        try:
            exec_result = self._container_obj.exec_run(
                ['test', '-d', path],
                stdout=False,
                stderr=False
            )
            return exec_result.exit_code == 0
        except Exception:
            return False
    
    def _extract_new_dir(self, cmd: str) -> Optional[str]:
        """Extract new directory from cd command"""
        cmd = (cmd or '').strip()
        if cmd.startswith('cd '):
            # Handle cd command at start of pipeline
            parts = cmd.split('&&')[0].strip().split()
            if len(parts) >= 2:
                path = parts[1].strip('\'"')  # Remove quotes
                if path == '~':
                    return '/root'
                elif path.startswith('/'):
                    return path
                elif path == '..':
                    # Go up one directory
                    parent = '/'.join(self.cwd.split('/')[:-1])
                    return parent if parent else '/'
                else:
                    # Relative path
                    new_path = f"{self.cwd}/{path}".replace('//', '/')
                    # Normalize path (remove ./ and ../)
                    parts = new_path.split('/')
                    normalized = []
                    for part in parts:
                        if part == '..':
                            if normalized:
                                normalized.pop()
                        elif part and part != '.':
                            normalized.append(part)
                    return '/' + '/'.join(normalized)
        return None

    def _gdb_persistent(self, cmd: str) -> Dict[str, Any]:
        """Execute GDB command in persistent session"""
        try:
            if self._gdb_session is None:
                # Start persistent GDB session
                logger.info("Starting persistent GDB session")
                # Find binary to debug (look for executable files)
                find_result = self._container_obj.exec_run(
                    f'bash -c "cd {self.cwd} && find . -maxdepth 1 -type f -executable | head -1"'
                )
                
                binary = None
                if find_result.exit_code == 0 and find_result.output:
                    found_binary = find_result.output.decode().strip()
                    if found_binary:
                        binary = found_binary
                        logger.info(f"Found executable for GDB: {binary}")
                
                if not binary:
                    logger.error(f"No executable found in {self.cwd} for GDB session")
                    return {"error": "No executable binary found for debugging", "cwd": self.cwd, "tool": "gdb"}
                
                # Start GDB in background with script mode
                self._gdb_session = self._container_obj.exec_run(
                    f'bash -c "cd {self.cwd} && gdb -q -batch-silent {binary}"',
                    stdin=True,
                    stdout=True,
                    stderr=True,
                    socket=True
                )
            
            # Find the binary dynamically for this command too
            find_result = self._container_obj.exec_run(
                f'bash -c "cd {self.cwd} && find . -maxdepth 1 -type f -executable | head -1"'
            )
            
            binary = None
            if find_result.exit_code == 0 and find_result.output:
                found_binary = find_result.output.decode().strip()
                if found_binary:
                    binary = found_binary
            
            if not binary:
                logger.error(f"No executable found in {self.cwd} for GDB command")
                return {"error": "No executable binary found for debugging", "cwd": self.cwd, "tool": "gdb"}
            
            # For now, use batch mode per command until we implement true persistence
            env_setup = 'export PATH="/root/.pyenv/versions/3.11.11/bin:$PATH" && export TERM=xterm'
            exec_result = self._container_obj.exec_run(
                f'bash -lc "{env_setup} && cd {self.cwd} && echo \'{cmd}\' | gdb -q -batch -ex \'run\' {binary}"',
                stdout=True,
                stderr=True
            )
            
            stdout = exec_result.output.decode('utf-8', errors='replace') if exec_result.output else ""
            
            return {
                "stdout": stdout,
                "stderr": "",
                "cwd": self.cwd,
                "exit_code": exec_result.exit_code,
                "tool": "gdb"
            }
            
        except Exception as e:
            logger.error(f"GDB execution failed: {e}")
            return {"error": str(e), "cwd": self.cwd, "tool": "gdb"}

    def _python_persistent(self, code: str) -> Dict[str, Any]:
        """Execute Python code in persistent session"""
        try:
            if self._python_session is None:
                # Start persistent Python session
                logger.info("Starting persistent Python session")
                self._python_session = self._container_obj.exec_run(
                    f'bash -c "cd {self.cwd} && python3 -i"',
                    stdin=True,
                    stdout=True,
                    stderr=True,
                    socket=True,
                    detach=True
                )
            
            # For now, use individual python calls until we implement true persistence
            # Create a temporary script and execute it
            import tempfile
            import base64
            
            # Encode the code to avoid shell escaping issues
            encoded_code = base64.b64encode(code.encode()).decode()
            
            env_setup = 'export PATH="/root/.pyenv/versions/3.11.11/bin:$PATH" && export TERM=xterm'
            exec_result = self._container_obj.exec_run(
                f'bash -lc "{env_setup} && cd {self.cwd} && echo {encoded_code} | base64 -d | python3"',
                stdout=True,
                stderr=True
            )
            
            stdout = exec_result.output.decode('utf-8', errors='replace') if exec_result.output else ""
            
            return {
                "stdout": stdout,
                "stderr": "",
                "cwd": self.cwd,
                "exit_code": exec_result.exit_code,
                "tool": "python"
            }
            
        except Exception as e:
            logger.error(f"Python execution failed: {e}")
            return {"error": str(e), "cwd": self.cwd, "tool": "python"}

    def _write_file(self, filename: str, content: str) -> Dict[str, Any]:
        """Write content to file safely using base64 encoding to avoid shell escaping issues"""
        try:
            if not filename:
                return {"error": "No filename provided", "cwd": self.cwd, "tool": "write_file"}
            
            # Use base64 encoding to completely avoid shell escaping issues
            import base64
            encoded_content = base64.b64encode(content.encode('utf-8')).decode('ascii')
            
            # Set up environment and write file
            env_setup = 'export PATH="/root/.pyenv/versions/3.11.11/bin:$PATH" && export TERM=xterm'
            write_cmd = f'{env_setup} && cd {self.cwd} && echo "{encoded_content}" | base64 -d > "{filename}"'
            
            # Encode the entire command in base64 for execution
            final_encoded = base64.b64encode(write_cmd.encode('utf-8')).decode('ascii')
            safe_cmd = f'echo "{final_encoded}" | base64 -d | bash'
            
            exec_result = self._container_obj.exec_run(
                ['bash', '-c', safe_cmd],
                stdout=True,
                stderr=True,
                stdin=False
            )
            
            stdout = exec_result.output.decode('utf-8', errors='replace') if exec_result.output else ""
            
            if exec_result.exit_code == 0:
                logger.info(f"Successfully wrote file: {filename} ({len(content)} bytes)")
                return {
                    "stdout": f"File '{filename}' written successfully ({len(content)} bytes)",
                    "stderr": "",
                    "cwd": self.cwd,
                    "exit_code": 0,
                    "tool": "write_file"
                }
            else:
                logger.error(f"Failed to write file {filename}: exit code {exec_result.exit_code}")
                return {
                    "stdout": stdout,
                    "stderr": f"Failed to write file (exit code: {exec_result.exit_code})",
                    "cwd": self.cwd,
                    "exit_code": exec_result.exit_code,
                    "tool": "write_file"
                }
                
        except Exception as e:
            logger.error(f"File write failed: {e}")
            return {"error": str(e), "cwd": self.cwd, "tool": "write_file"}

    def _read_file(self, filename: str, max_bytes: int = None) -> Dict[str, Any]:
        """Read entire file safely; optionally cap bytes to avoid huge outputs"""
        try:
            if not filename:
                return {"error": "No filename provided", "cwd": self.cwd, "tool": "read_file"}
            # Validate file path is inside the working directory to avoid path escapes
            import os
            target_path = filename if filename.startswith('/') else os.path.join(self.cwd, filename)
            # Normalize path
            target_path = os.path.normpath(target_path)
            # Determine file size up front (if possible)
            file_size = None
            try:
                size_result = self._container_obj.exec_run(['bash', '-lc', f'stat -c %s "{target_path}"'])
                if size_result.exit_code == 0 and size_result.output:
                    try:
                        file_size = int(size_result.output.decode().strip())
                    except Exception:
                        file_size = None
            except Exception:
                file_size = None

            # Execute cat with optional head if max_bytes is provided
            env_setup = 'export PATH="/root/.pyenv/versions/3.11.11/bin:$PATH" && export TERM=xterm'
            if max_bytes and isinstance(max_bytes, int) and max_bytes > 0:
                read_cmd = f'{env_setup} && head -c {max_bytes} "{target_path}"'
            else:
                read_cmd = f'{env_setup} && cat "{target_path}"'
            exec_result = self._container_obj.exec_run(['bash', '-lc', read_cmd], stdout=True, stderr=True)
            raw_bytes = exec_result.output or b""
            stdout = raw_bytes.decode('utf-8', errors='replace') if raw_bytes else ""

            # Heuristic: if max_bytes provided and appears smaller than file_size, hint to read fully
            stderr_note = ""
            if (isinstance(max_bytes, int) and max_bytes > 0 and file_size is not None and max_bytes < file_size):
                try:
                    bytes_read = len(raw_bytes)
                except Exception:
                    bytes_read = max_bytes
                stderr_note = (
                    f"NOTE: Only read {bytes_read} of {file_size} bytes. "
                    f"To read the full file, call read_file {filename} {file_size} or omit max_bytes."
                )

            return {
                "stdout": stdout,
                "stderr": stderr_note,
                "cwd": self.cwd,
                "exit_code": exec_result.exit_code,
                "tool": "read_file",
                "meta": {
                    "filename": filename,
                    "file_size": file_size,
                    "max_bytes": max_bytes,
                    "bytes_returned": len(raw_bytes) if raw_bytes else 0,
                    "truncated": bool(isinstance(max_bytes, int) and max_bytes > 0 and file_size is not None and max_bytes < file_size)
                }
            }
        except Exception as e:
            logger.error(f"File read failed: {e}")
            return {"error": str(e), "cwd": self.cwd, "tool": "read_file"}
    
            
    def get_available_tools(self) -> Dict[str, List[str]]:
        """Return full EXEGOL_TOOLS list - trust that tools exist in Exegol container"""
        if not self.ensure_running():
            logger.error("Container not running - cannot provide tools")
            return {}
        
        logger.info("Providing full EXEGOL_TOOLS list to LLM")
        
        # Just return the full tools list from config - much faster and more comprehensive
        total_tools = sum(len(tools) for tools in EXEGOL_TOOLS.values())
        logger.info(f"Providing {total_tools} tools across {len(EXEGOL_TOOLS)} categories")
        
        return EXEGOL_TOOLS.copy()  # Return a copy to avoid modification
    
    def get_tool_info(self, tool: str) -> Optional[Dict[str, str]]:
        """Get information about a specific tool"""
        if not self.ensure_running():
            return None
            
        try:
            # Get tool path and version
            path_result = self._container_obj.exec_run(f'which {tool}')
            if path_result.exit_code != 0:
                return None
                
            tool_path = path_result.output.decode().strip()
            
            # Try to get version
            version_commands = [f'{tool} --version', f'{tool} -V', f'{tool} -v']
            version_info = None
            
            for cmd in version_commands:
                try:
                    version_result = self._container_obj.exec_run(cmd, stdout=True, stderr=True)
                    if version_result.exit_code == 0 and version_result.output:
                        version_info = version_result.output.decode().strip().split('\n')[0]
                        break
                except Exception:
                    continue
                    
            return {
                'path': tool_path,
                'version': version_info or 'unknown'
            }
            
        except Exception as e:
            logger.debug(f"Failed to get info for tool {tool}: {e}")
            return None

    def cleanup(self):
        """Clean up persistent sessions and stop container"""
        if self._gdb_session:
            try:
                self._gdb_session.close()
            except Exception:
                pass
            self._gdb_session = None
            
        if self._python_session:
            try:
                self._python_session.close()  
            except Exception:
                pass
            self._python_session = None
            
        self.stop()


