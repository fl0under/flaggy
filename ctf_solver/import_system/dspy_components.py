"""
DSPy components for the challenge import pipeline
"""
import dspy
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from .schemas import ExtractedChallenge, ImportSourceType, ChallengeCategory, DifficultyLevel


class URLAnalysisResult(BaseModel):
    """Result of URL analysis"""
    source_type: ImportSourceType
    platform_name: Optional[str] = None
    requires_auth: bool = False
    auth_type: Optional[str] = None  # "login", "token", "basic"
    is_multi_challenge: bool = False
    confidence: float = 0.0


class URLAnalyzer(dspy.Signature):
    """
    Analyze a URL to determine the source type and authentication requirements
    """
    url: str = dspy.InputField(desc="URL to analyze")
    page_content: str = dspy.InputField(desc="HTML content of the page (first 2000 chars)")
    
    source_type: str = dspy.OutputField(desc="Type of source: ctfd, github, web_page, archive, file")
    platform_name: str = dspy.OutputField(desc="Name of the platform/CTF if identifiable")
    requires_auth: bool = dspy.OutputField(desc="Whether the page requires authentication")
    auth_type: str = dspy.OutputField(desc="Type of auth needed: login, token, basic, or none")
    is_multi_challenge: bool = dspy.OutputField(desc="Whether this page contains multiple challenges")
    confidence: float = dspy.OutputField(desc="Confidence in analysis (0.0-1.0)")


class ChallengeDetector(dspy.Signature):
    """
    Detect individual challenges in page content
    """
    url: str = dspy.InputField(desc="Source URL")
    page_content: str = dspy.InputField(desc="Full HTML content of the page")
    platform_type: str = dspy.InputField(desc="Detected platform type")
    
    challenge_count: int = dspy.OutputField(desc="Number of challenges found on the page")
    challenge_links: str = dspy.OutputField(desc="JSON list of links to individual challenges")
    needs_individual_fetch: bool = dspy.OutputField(desc="Whether each challenge needs separate fetching")


class ChallengeExtractor(dspy.Signature):
    """
    Extract challenge information from page content
    """
    url: str = dspy.InputField(desc="URL of the challenge page")
    page_content: str = dspy.InputField(desc="HTML content of the challenge page")
    platform_type: str = dspy.InputField(desc="Type of platform (ctfd, github, etc)")
    
    name: str = dspy.OutputField(desc="Challenge name")
    description: str = dspy.OutputField(desc="Challenge description/prompt")
    category: str = dspy.OutputField(desc="Challenge category (pwn, crypto, web, etc)")
    difficulty: str = dspy.OutputField(desc="Difficulty level (easy, medium, hard, etc)")
    points: int = dspy.OutputField(desc="Point value (0 if not specified)")
    flag_format: str = dspy.OutputField(desc="Expected flag format pattern")
    file_links: str = dspy.OutputField(desc="JSON list of downloadable file URLs")
    author: str = dspy.OutputField(desc="Challenge author if mentioned")
    additional_info: str = dspy.OutputField(desc="Any additional relevant information")


class FlagExtractor(dspy.Signature):
    """
    Extract flag from challenge page or solution
    """
    url: str = dspy.InputField(desc="URL of the page")
    page_content: str = dspy.InputField(desc="HTML content to search for flags")
    flag_format: str = dspy.InputField(desc="Expected flag format pattern")
    
    flag_found: bool = dspy.OutputField(desc="Whether a flag was found")
    flag_value: str = dspy.OutputField(desc="The flag value if found")
    flag_location: str = dspy.OutputField(desc="Where the flag was found (description, comment, etc)")


class MetadataRefiner(dspy.Signature):
    """
    Refine and standardize extracted challenge metadata
    """
    raw_challenge: str = dspy.InputField(desc="JSON of raw extracted challenge data")
    
    refined_name: str = dspy.OutputField(desc="Cleaned and standardized challenge name")
    refined_category: str = dspy.OutputField(desc="Standardized category from allowed list")
    refined_difficulty: str = dspy.OutputField(desc="Standardized difficulty level")
    refined_description: str = dspy.OutputField(desc="Cleaned challenge description")
    suggested_tags: str = dspy.OutputField(desc="JSON list of suggested tags")
    estimated_solve_time: int = dspy.OutputField(desc="Estimated solve time in minutes")
    prerequisites: str = dspy.OutputField(desc="JSON list of required skills/tools")


class ImportPipeline:
    """
    Main DSPy-powered import pipeline
    """
    
    def __init__(self):
        self.url_analyzer = dspy.ChainOfThought(URLAnalyzer)
        self.challenge_detector = dspy.ChainOfThought(ChallengeDetector) 
        self.challenge_extractor = dspy.ChainOfThought(ChallengeExtractor)
        self.flag_extractor = dspy.ChainOfThought(FlagExtractor)
        self.metadata_refiner = dspy.ChainOfThought(MetadataRefiner)
    
    def analyze_url(self, url: str, page_content: str) -> URLAnalysisResult:
        """Analyze URL to determine source type and requirements"""
        result = self.url_analyzer(url=url, page_content=page_content[:2000])
        
        return URLAnalysisResult(
            source_type=ImportSourceType(result.source_type),
            platform_name=result.platform_name if result.platform_name != "unknown" else None,
            requires_auth=result.requires_auth,
            auth_type=result.auth_type if result.auth_type != "none" else None,
            is_multi_challenge=result.is_multi_challenge,
            confidence=result.confidence
        )
    
    def detect_challenges(self, url: str, page_content: str, platform_type: str) -> List[str]:
        """Detect individual challenges on a page"""
        result = self.challenge_detector(
            url=url, 
            page_content=page_content,
            platform_type=platform_type
        )
        
        try:
            import json
            challenge_links = json.loads(result.challenge_links)
            return challenge_links
        except:
            # Fallback: return original URL if parsing fails
            return [url]
    
    def extract_challenge(self, url: str, page_content: str, platform_type: str) -> ExtractedChallenge:
        """Extract challenge information from a single challenge page"""
        result = self.challenge_extractor(
            url=url,
            page_content=page_content,
            platform_type=platform_type
        )
        
        # Parse file links
        file_links = []
        try:
            import json
            file_links = json.loads(result.file_links)
        except:
            pass
        
        return ExtractedChallenge(
            name=result.name,
            description=result.description,
            category=result.category,
            difficulty=result.difficulty,
            points=result.points if result.points > 0 else None,
            file_urls=file_links,
            source_url=url,
            additional_context={
                "author": result.author,
                "flag_format": result.flag_format,
                "additional_info": result.additional_info
            }
        )
    
    def extract_flag(self, url: str, page_content: str, flag_format: str) -> Optional[str]:
        """Try to extract flag from page content"""
        result = self.flag_extractor(
            url=url,
            page_content=page_content,
            flag_format=flag_format
        )
        
        if result.flag_found:
            return result.flag_value
        return None
    
    def refine_metadata(self, extracted_challenge: ExtractedChallenge) -> Dict[str, Any]:
        """Refine and standardize challenge metadata"""
        import json
        
        raw_data = json.dumps(extracted_challenge.dict())
        result = self.metadata_refiner(raw_challenge=raw_data)
        
        # Parse structured outputs
        tags = []
        prerequisites = []
        try:
            tags = json.loads(result.suggested_tags)
            prerequisites = json.loads(result.prerequisites)
        except:
            pass
        
        # Map common category variations to our enum values
        category_mapping = {
            'binary exploitation': 'pwn',
            'binary exploitation (pwn)': 'pwn', 
            'pwn': 'pwn',
            'pwning': 'pwn',
            'exploitation': 'pwn',
            'reverse engineering': 'reverse',
            'reverse': 'reverse',
            'rev': 'reverse',
            'reversing': 'reverse',
            'cryptography': 'crypto',
            'crypto': 'crypto',
            'web exploitation': 'web',
            'web': 'web',
            'web security': 'web',
            'forensics': 'forensics',
            'digital forensics': 'forensics',
            'misc': 'misc',
            'miscellaneous': 'misc',
            'osint': 'osint',
            'steganography': 'stego',
            'stego': 'stego'
        }
        
        refined_category = result.refined_category.lower()
        mapped_category = category_mapping.get(refined_category, 'misc')
        
        return {
            "name": result.refined_name,
            "category": mapped_category,
            "difficulty": result.refined_difficulty.lower(),
            "description": result.refined_description,
            "tags": tags,
            "estimated_solve_time": result.estimated_solve_time,
            "prerequisites": prerequisites
        }