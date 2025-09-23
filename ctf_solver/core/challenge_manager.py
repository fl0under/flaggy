"""
Challenge management system for flaggy
"""
import os
import json
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ctf_solver.database.db import get_db_cursor


logger = logging.getLogger(__name__)


class ChallengeManager:
    def __init__(self, base_dir: str = "/root/flaggy"):
        self.base_dir = Path(base_dir)
        self.challenges_dir = self.base_dir / "challenges"
        self.work_dir = self.base_dir / "work"
        
        # Ensure directories exist
        self.challenges_dir.mkdir(exist_ok=True)
        self.work_dir.mkdir(exist_ok=True)
    
    def discover_challenges(self) -> List[Dict[str, any]]:
        """Scan challenges directory and return list of discovered challenges"""
        challenges = []
        
        if not self.challenges_dir.exists():
            logger.warning(f"Challenges directory not found: {self.challenges_dir}")
            return challenges
        
        for challenge_dir in self.challenges_dir.iterdir():
            if not challenge_dir.is_dir():
                continue
                
            challenge_info = self._analyze_challenge_dir(challenge_dir)
            if challenge_info:
                challenges.append(challenge_info)
                
        logger.info(f"Discovered {len(challenges)} challenges")
        return challenges
    
    def _analyze_challenge_dir(self, challenge_dir: Path) -> Optional[Dict[str, any]]:
        """Analyze a challenge directory and extract metadata"""
        try:
            name = challenge_dir.name
            
            # Look for metadata file (try new format first, then legacy)
            metadata = {}
            challenge_json = challenge_dir / "challenge.json"
            metadata_json = challenge_dir / "metadata.json"
            
            if challenge_json.exists():
                # New format with challenge.json
                with open(challenge_json) as f:
                    metadata = json.load(f)
            elif metadata_json.exists():
                # Legacy format with metadata.json
                with open(metadata_json) as f:
                    metadata = json.load(f)
            
            # Find the main challenge file from include_files metadata
            main_file = None
            if 'include_files' in metadata:
                include_patterns = metadata['include_files']
                # Handle new format where include_files might be ["*"] or a list of actual files
                if include_patterns and include_patterns != ["*"]:
                    for pattern in include_patterns:
                        # Find first non-wildcard file as main file
                        if not pattern.startswith('*'):
                            candidate_path = challenge_dir / pattern
                            if candidate_path.exists():
                                main_file = str(candidate_path)
                                break
            
            # Fallback: look for common challenge file names or any executable
            if not main_file:
                common_names = ['vuln', 'challenge', 'binary', 'pwn', f'{name}.py', f'{name}.js', name]
                
                # First try common names
                for candidate in common_names:
                    candidate_path = challenge_dir / candidate
                    if candidate_path.exists():
                        main_file = str(candidate_path)
                        break
                
                # If still no main file, look for any executable file
                if not main_file:
                    for file_path in challenge_dir.iterdir():
                        if file_path.is_file() and os.access(file_path, os.X_OK):
                            main_file = str(file_path)
                            logger.info(f"Using executable file as main: {file_path.name}")
                            break
                
                # Last resort: use any non-metadata file
                if not main_file:
                    for file_path in challenge_dir.iterdir():
                        if (file_path.is_file() and 
                            file_path.name not in ['challenge.json', 'metadata.json', 'solution.json', 'description.txt']):
                            main_file = str(file_path)
                            logger.info(f"Using first available file as main: {file_path.name}")
                            break
            
            # If still no main file, create a placeholder
            if not main_file:
                logger.info(f"No obvious main file found in {challenge_dir}, using directory as placeholder")
                main_file = str(challenge_dir / "challenge")  # Placeholder that points to directory
            
            # Look for description
            description = metadata.get('description', '')
            desc_file = challenge_dir / "description.txt"
            if desc_file.exists() and not description:
                description = desc_file.read_text().strip()
            
            return {
                'name': name,
                'binary_path': main_file,  # Main challenge file (binary or source)
                'directory': str(challenge_dir),
                'description': description,
                'category': metadata.get('category', 'misc'),
                'flag_format': metadata.get('flag_format', 'picoCTF{.*}'),
                'points': metadata.get('points', 100)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing challenge {challenge_dir}: {e}")
            return None
    
    def sync_challenges_to_db(self):
        """Import discovered challenges to database"""
        challenges = self.discover_challenges()
        
        with get_db_cursor() as cursor:
            for challenge in challenges:
                # Check if challenge already exists
                cursor.execute(
                    "SELECT id FROM challenges WHERE name = %s",
                    (challenge['name'],)
                )
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing challenge
                    cursor.execute("""
                        UPDATE challenges 
                        SET binary_path = %s, description = %s, category = %s, 
                            flag_format = %s
                        WHERE name = %s
                    """, (
                        challenge['binary_path'],
                        challenge['description'],
                        challenge['category'],
                        challenge['flag_format'],
                        challenge['name']
                    ))
                    logger.info(f"Updated challenge: {challenge['name']}")
                else:
                    # Insert new challenge
                    cursor.execute("""
                        INSERT INTO challenges 
                        (name, binary_path, description, category, flag_format)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        challenge['name'],
                        challenge['binary_path'],
                        challenge['description'],
                        challenge['category'],
                        challenge['flag_format']
                    ))
                    logger.info(f"Added new challenge: {challenge['name']}")
    
    def prepare_attempt_workspace(self, challenge_id: int, attempt_id: int) -> Tuple[str, Dict[str, str]]:
        """
        Prepare working directory for an attempt
        Returns: (work_directory_path, container_mounts)
        """
        # Get challenge info from database
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT name, binary_path FROM challenges WHERE id = %s
            """, (challenge_id,))
            result = cursor.fetchone()
            
            if not result:
                raise ValueError(f"Challenge {challenge_id} not found")
            
            challenge_name, binary_path = result
        
        # Create attempt working directory (clean it first if it exists)
        attempt_dir = self.work_dir / f"attempt_{attempt_id}"
        if attempt_dir.exists():
            logger.info(f"Cleaning existing workspace directory {attempt_dir}")
            shutil.rmtree(attempt_dir)
        attempt_dir.mkdir(exist_ok=False)
        
        # Get challenge directory
        challenge_dir = Path(binary_path).parent
        
        # Copy challenge files based on inclusion/exclusion rules
        copied_files = []
        excluded_files = []
        
        for file_path in challenge_dir.iterdir():
            if file_path.is_file():
                if self._should_copy_file(file_path, challenge_dir):
                    dest_path = attempt_dir / file_path.name
                    shutil.copy2(file_path, dest_path)
                    copied_files.append(file_path.name)
                    logger.debug(f"Copied {file_path.name} to attempt workspace")
                else:
                    excluded_files.append(file_path.name)
                    logger.debug(f"Excluded {file_path.name} from attempt workspace")
        
        logger.info(f"Copied {len(copied_files)} files, excluded {len(excluded_files)} files")
        
        # Prepare container mounts (host_path -> container_path)  
        # Only mount the filtered working copy - no access to raw source files
        container_mounts = {
            str(attempt_dir): '/challenge'               # read-write working copy (filtered)
        }
        
        logger.info(f"Prepared workspace for attempt {attempt_id} at {attempt_dir}")
        return str(attempt_dir), container_mounts
    
    def get_challenge_files(self, challenge_id: int) -> List[str]:
        """Get list of files in a challenge directory"""
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT binary_path FROM challenges WHERE id = %s
            """, (challenge_id,))
            result = cursor.fetchone()
            
            if not result:
                return []
            
            challenge_dir = Path(result[0]).parent
            return [f.name for f in challenge_dir.iterdir() if f.is_file()]
    
    def cleanup_attempt_workspace(self, attempt_id: int, keep_successful: bool = True):
        """
        Clean up attempt workspace (optional - by default we keep everything)
        """
        attempt_dir = self.work_dir / f"attempt_{attempt_id}"
        if attempt_dir.exists():
            if keep_successful:
                logger.info(f"Keeping attempt workspace: {attempt_dir}")
                return
            else:
                shutil.rmtree(attempt_dir)
                logger.info(f"Cleaned up attempt workspace: {attempt_dir}")
    
    def _should_copy_file(self, file_path: Path, challenge_dir: Path) -> bool:
        """
        Determine if a file should be copied to the working directory
        Uses metadata.json include/exclude rules with wildcard support
        """
        filename = file_path.name
        relative_path = file_path.relative_to(challenge_dir).as_posix()
        
        # Check for metadata-based rules (try new format first, then legacy)
        challenge_json = challenge_dir / "challenge.json"
        metadata_json = challenge_dir / "metadata.json"
        
        metadata = {}
        if challenge_json.exists():
            try:
                with open(challenge_json) as f:
                    metadata = json.load(f)
            except Exception as e:
                logger.warning(f"Error reading challenge.json for file filtering: {e}")
        elif metadata_json.exists():
            try:
                with open(metadata_json) as f:
                    metadata = json.load(f)
            except Exception as e:
                logger.warning(f"Error reading metadata.json for file filtering: {e}")
        
        if metadata:
            # Priority 1: Check exclusions first (always respected)
            if 'exclude_files' in metadata:
                if self._matches_any_pattern(relative_path, metadata['exclude_files']):
                    return False
            
            # Priority 2: Explicit include list (if provided, only these files)
            if 'include_files' in metadata:
                return self._matches_any_pattern(relative_path, metadata['include_files'])
            
            # No include list, fall through to default rules
        
        # Priority 3: Default rules
        return self._apply_default_rules(file_path)
    
    def _matches_any_pattern(self, filepath: str, patterns: List[str]) -> bool:
        """Check if filepath matches any of the given patterns with wildcard support"""
        import fnmatch
        
        for pattern in patterns:
            # Support both filename-only and full relative path matching
            if self._matches_pattern(filepath, pattern) or self._matches_pattern(Path(filepath).name, pattern):
                return True
        return False
    
    def _matches_pattern(self, filepath: str, pattern: str) -> bool:
        """Pattern matching with wildcard support"""
        import fnmatch
        
        # Handle directory patterns (src/** matches src/foo/bar.c)
        if pattern.endswith('/**'):
            dir_pattern = pattern[:-3]
            return filepath.startswith(dir_pattern + '/') or filepath == dir_pattern
        
        # Handle directory contents (src/* matches src/file.c but not src/sub/file.c)  
        if pattern.endswith('/*'):
            dir_pattern = pattern[:-2]
            path_parts = filepath.split('/')
            return len(path_parts) == 2 and path_parts[0] == dir_pattern
        
        # Standard fnmatch for files and simple patterns
        return fnmatch.fnmatch(filepath, pattern)
    
    def _apply_default_rules(self, file_path: Path) -> bool:
        """Apply built-in default filtering rules"""
        filename = file_path.name
        suffix = file_path.suffix.lower()
        
        # Always exclude common development/debug files and sensitive files
        always_exclude = {
            '.git', '.gitignore', '.flaggyignore', 
            'README.md', 'readme.txt',
            'Makefile', 'makefile',
            '.DS_Store', 'Thumbs.db',
            'solution.json'  # Never copy solution file to container
        }
        
        if filename.lower() in always_exclude:
            return False
        
        # Exclude source code files (unless specifically needed)
        source_extensions = {'.c', '.cpp', '.cc', '.cxx', '.h', '.hpp', 
                           '.py', '.java', '.rs', '.go', '.js', '.asm', '.s'}
        
        # Exception: if there's only source files and no binaries, include them
        challenge_dir = file_path.parent
        has_executables = any(
            f.is_file() and os.access(f, os.X_OK) and f.suffix not in source_extensions
            for f in challenge_dir.iterdir()
        )
        
        if suffix in source_extensions:
            if has_executables:
                # Has binaries, exclude source by default
                return False
            else:
                # No binaries found, include source files
                return True
        
        # Include everything else (binaries, data files, etc.)
        return True