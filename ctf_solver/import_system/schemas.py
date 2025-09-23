"""
Data schemas for challenge metadata and import system
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum


class DifficultyLevel(str, Enum):
    """Standard difficulty levels"""
    TRIVIAL = "trivial"
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"


class ChallengeCategory(str, Enum):
    """Standard CTF categories"""
    PWN = "pwn"
    REVERSE = "reverse"
    CRYPTO = "crypto"
    WEB = "web"
    FORENSICS = "forensics"
    MISC = "misc"
    OSINT = "osint"
    STEGO = "stego"
    HARDWARE = "hardware"


class FileMapping(BaseModel):
    """Describes how a file should be handled in the container"""
    filename: str
    destination_path: str = "/challenge"
    permissions: Optional[str] = None
    executable: bool = False


class ChallengeMetadata(BaseModel):
    """
    Metadata for a challenge that gets copied to the container
    This file is visible to the solving agent
    """
    name: str = Field(description="Challenge name")
    description: str = Field(description="Challenge description/prompt")
    category: ChallengeCategory = Field(description="Challenge category")
    difficulty: DifficultyLevel = Field(description="Difficulty level")
    
    # Source information
    source_url: Optional[HttpUrl] = Field(None, description="Original source URL")
    source_platform: Optional[str] = Field(None, description="Platform/CTF name")
    author: Optional[str] = Field(None, description="Challenge author")
    event_name: Optional[str] = Field(None, description="CTF event name")
    
    # Challenge specifics
    flag_format: str = Field(default="flag{.*}", description="Regex pattern for flag format")
    points: Optional[int] = Field(None, description="Point value")
    tags: List[str] = Field(default_factory=list, description="Additional tags")
    
    # Solving hints (for agent)
    estimated_solve_time: Optional[int] = Field(None, description="Estimated solve time in minutes")
    prerequisites: List[str] = Field(default_factory=list, description="Required skills/tools")
    hints: List[str] = Field(default_factory=list, description="Hints for solving")
    
    # File handling
    include_files: List[str] = Field(default_factory=list, description="Files to copy to container")
    exclude_files: List[str] = Field(default_factory=list, description="Files to exclude from container")
    file_mappings: List[FileMapping] = Field(default_factory=list, description="Custom file mappings")
    
    # Metadata
    imported_at: datetime = Field(default_factory=datetime.now, description="Import timestamp")
    flaggy_version: str = Field(default="1.0", description="Flaggy version that imported this")


class ChallengeSolution(BaseModel):
    """
    Solution data that is NEVER copied to the container
    This file contains sensitive information for validation
    """
    challenge_name: str = Field(description="Name of the challenge")
    flag: str = Field(description="The actual flag")
    
    # Solution metadata
    solution_approach: Optional[str] = Field(None, description="High-level solution approach")
    writeup_url: Optional[HttpUrl] = Field(None, description="Link to detailed writeup")
    solver_notes: List[str] = Field(default_factory=list, description="Internal solver notes")
    
    # Validation
    test_inputs: List[Dict[str, Any]] = Field(default_factory=list, description="Test cases for validation")
    success_indicators: List[str] = Field(default_factory=list, description="Signs of successful exploitation")
    
    # Import metadata
    imported_at: datetime = Field(default_factory=datetime.now)
    source_url: Optional[HttpUrl] = Field(None, description="Where this was imported from")


class ImportSourceType(str, Enum):
    """Types of import sources"""
    CTFD = "ctfd"           # CTFd platform
    GITHUB = "github"       # GitHub repository
    WEB_PAGE = "web_page"   # Generic web page
    ARCHIVE = "archive"     # Archive.org or similar
    FILE = "file"           # Local file/directory


class ImportRequest(BaseModel):
    """Request to import challenges from a source"""
    url: HttpUrl = Field(description="Source URL to import from")
    source_type: Optional[ImportSourceType] = Field(None, description="Source type (auto-detected if None)")
    
    # Authentication
    username: Optional[str] = Field(None, description="Username for authenticated access")
    password: Optional[str] = Field(None, description="Password for authenticated access")
    api_token: Optional[str] = Field(None, description="API token for authenticated access")
    
    # Import options
    challenge_filter: Optional[str] = Field(None, description="Regex filter for challenge names")
    category_filter: List[ChallengeCategory] = Field(default_factory=list, description="Only import these categories")
    max_challenges: Optional[int] = Field(None, description="Maximum number of challenges to import")
    
    # File download options
    download_files: bool = Field(default=True, description="Whether to download challenge files")
    confirm_downloads: bool = Field(default=False, description="Ask for user confirmation before downloading files")
    max_file_size: int = Field(default=100*1024*1024, description="Maximum file size to download (bytes)")


class ImportResult(BaseModel):
    """Result of an import operation"""
    success: bool
    challenges_imported: int = 0
    challenges_failed: int = 0
    error_message: Optional[str] = None
    imported_challenges: List[str] = Field(default_factory=list, description="Names of successfully imported challenges")
    failed_challenges: List[Dict[str, str]] = Field(default_factory=list, description="Failed challenges with error messages")
    
    # Statistics
    total_files_downloaded: int = 0
    total_download_size: int = 0
    import_duration: Optional[float] = None


class ExtractedChallenge(BaseModel):
    """
    Raw challenge data extracted from a source before processing
    Used internally by the import pipeline
    """
    name: str
    description: str
    category: Optional[str] = None
    difficulty: Optional[str] = None
    points: Optional[int] = None
    flag: Optional[str] = None
    
    # Files
    file_urls: List[str] = Field(default_factory=list, description="URLs of challenge files to download")
    attachment_links: List[str] = Field(default_factory=list, description="Direct attachment links")
    
    # Source context
    source_url: Optional[str] = None
    raw_html: Optional[str] = None
    additional_context: Dict[str, Any] = Field(default_factory=dict)