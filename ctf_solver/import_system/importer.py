"""
Main challenge importer with file handling and processing logic
"""
import os
import json
import requests
import logging
import tempfile
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse
from datetime import datetime

from .schemas import (
    ImportRequest, ImportResult, ExtractedChallenge, 
    ChallengeMetadata, ChallengeSolution, ImportSourceType,
    ChallengeCategory, DifficultyLevel
)
from .dspy_components import ImportPipeline
from .file_downloader import FileDownloader
from ..config import configure_dspy


logger = logging.getLogger(__name__)


class ChallengeImporter:
    """
    Main challenge importer that orchestrates the import process
    """
    
    def __init__(self, base_challenges_dir: str = "/root/flaggy/challenges"):
        self.challenges_dir = Path(base_challenges_dir)
        self.challenges_dir.mkdir(exist_ok=True)
        
        # Configure DSPy before creating pipeline
        configure_dspy()
        
        self.pipeline = ImportPipeline()
        self.file_downloader = FileDownloader()
        
        # Session for web requests with reasonable defaults
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Flaggy-CTF-Importer/1.0 (Educational Use)'
        })
    
    def import_challenges(self, request: ImportRequest) -> ImportResult:
        """
        Import challenges from the specified source
        """
        start_time = datetime.now()
        result = ImportResult(success=False)
        
        try:
            logger.info(f"Starting import from {request.url}")

            # Special-case: DUCTF Archives static export (client-hydrated site)
            try:
                handled = self._try_import_ductf_archives(str(request.url), request, result)
                if handled:
                    result.success = result.challenges_imported > 0
                    result.import_duration = (datetime.now() - start_time).total_seconds()
                    logger.info(f"Import completed (DUCTF Archives): {result.challenges_imported} successful, {result.challenges_failed} failed")
                    return result
            except Exception as e:
                logger.warning(f"DUCTF Archives fast-path failed; falling back to generic pipeline: {e}")
            
            # Step 1: Fetch initial page content
            page_content = self._fetch_page_content(str(request.url), request)
            if not page_content:
                result.error_message = "Failed to fetch page content"
                return result
            
            # Special-case: Generic NoCTF static export detection via assets base
            try:
                handled_noctf = self._try_import_noctf_static(str(request.url), page_content, request, result)
                if handled_noctf:
                    result.success = result.challenges_imported > 0
                    result.import_duration = (datetime.now() - start_time).total_seconds()
                    logger.info(f"Import completed (NoCTF static): {result.challenges_imported} successful, {result.challenges_failed} failed")
                    return result
            except Exception as e:
                logger.warning(f"NoCTF static fast-path failed; continuing with generic pipeline: {e}")
            
            # Step 2: Analyze URL and determine source type
            analysis = self.pipeline.analyze_url(str(request.url), page_content)
            logger.info(f"Detected source type: {analysis.source_type}, multi-challenge: {analysis.is_multi_challenge}")
            
            # Step 3: Handle authentication if required
            if analysis.requires_auth and not self._handle_authentication(request, analysis):
                result.error_message = "Authentication failed"
                return result
            
            # Step 4: Detect and extract challenges
            if analysis.is_multi_challenge:
                challenge_urls = self.pipeline.detect_challenges(
                    str(request.url), page_content, analysis.source_type
                )
            else:
                challenge_urls = [str(request.url)]
            
            # Apply filters
            if request.max_challenges:
                challenge_urls = challenge_urls[:request.max_challenges]
            
            logger.info(f"Found {len(challenge_urls)} challenge(s) to process")
            
            # Step 5: Process each challenge
            for i, challenge_url in enumerate(challenge_urls):
                try:
                    logger.info(f"Processing challenge {i+1}/{len(challenge_urls)}: {challenge_url}")
                    
                    # Fetch individual challenge page if needed
                    if challenge_url != str(request.url):
                        challenge_content = self._fetch_page_content(challenge_url, request)
                    else:
                        challenge_content = page_content
                    
                    if not challenge_content:
                        logger.warning(f"Failed to fetch content for {challenge_url}")
                        result.failed_challenges.append({
                            "url": challenge_url,
                            "error": "Failed to fetch content"
                        })
                        result.challenges_failed += 1
                        continue
                    
                    # Extract challenge data
                    extracted = self.pipeline.extract_challenge(
                        challenge_url, challenge_content, analysis.source_type
                    )
                    
                    # Apply filters
                    if not self._passes_filters(extracted, request):
                        logger.info(f"Challenge {extracted.name} filtered out")
                        continue
                    
                    # Import the challenge
                    success, download_stats = self._import_single_challenge(extracted, request, analysis)
                    if success:
                        result.total_files_downloaded += download_stats.get('files_downloaded', 0)
                        result.imported_challenges.append(extracted.name)
                        result.challenges_imported += 1
                        logger.info(f"Successfully imported {extracted.name}")
                    else:
                        result.failed_challenges.append({
                            "name": extracted.name,
                            "error": "Import processing failed"
                        })
                        result.challenges_failed += 1
                    
                except Exception as e:
                    logger.error(f"Error processing challenge {challenge_url}: {e}")
                    result.failed_challenges.append({
                        "url": challenge_url,
                        "error": str(e)
                    })
                    result.challenges_failed += 1
            
            # Step 6: Finalize results
            result.success = result.challenges_imported > 0
            end_time = datetime.now()
            result.import_duration = (end_time - start_time).total_seconds()
            
            logger.info(f"Import completed: {result.challenges_imported} successful, {result.challenges_failed} failed")
            return result
            
        except Exception as e:
            logger.error(f"Import failed with error: {e}")
            result.error_message = str(e)
            return result

    def _try_import_ductf_archives(self, url: str, request: ImportRequest, result: ImportResult) -> bool:
        """Detect and import from DUCTF Archives static export if applicable.

        Returns True if this method handled the import (successfully or not),
        otherwise False to let the generic flow continue.
        """
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if not hostname.endswith("archives.duc.tf"):
            return False

        # Expect pattern like 2025.archives.duc.tf
        subdomain = hostname.split(".")[0]
        if not subdomain.isdigit() or len(subdomain) != 4:
            # Not a year subdomain; skip
            return False

        year = subdomain
        export_base = f"https://archives.duc.tf/{year}/export"

        # Read static export JSONs
        def _get_json(path: str) -> Optional[Dict[str, Any]]:
            try:
                resp = self.session.get(f"{export_base}/{path}", timeout=30)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.error(f"Failed to fetch {export_base}/{path}: {e}")
                return None

        challenges_idx = _get_json("challenges.json")
        details_list = _get_json("challenge_details.json")
        if not challenges_idx or not isinstance(challenges_idx.get("data"), dict):
            return False
        if not details_list or not isinstance(details_list, list):
            return False

        # Optional slug filter from query ?c=slug
        qs = parse_qs(parsed.query)
        slug_filter = (qs.get("c") or [None])[0]

        challenges = challenges_idx["data"].get("challenges", [])
        if slug_filter:
            challenges = [c for c in challenges if c.get("slug") == slug_filter]
        if request.max_challenges:
            challenges = challenges[: request.max_challenges]

        logger.info(f"DUCTF Archives: {len(challenges)} candidate challenge(s)")

        # Index details by id for quick lookup
        details_by_id: Dict[int, Dict[str, Any]] = {}
        for entry in details_list:
            try:
                cid = int(entry.get("data", {}).get("id"))
                details_by_id[cid] = entry
            except Exception:
                continue

        # Process each selected challenge
        for c in challenges:
            try:
                cid = int(c.get("id"))
                slug = c.get("slug") or str(cid)
                title = c.get("title") or slug
                value = c.get("value")
                tags = c.get("tags", {}) or {}
                category = (tags.get("categories") or "misc").lower()
                difficulty = (tags.get("difficulty") or "medium").lower()

                details = details_by_id.get(cid, {})
                data = details.get("data", {})
                description = data.get("description") or ""
                metadata = data.get("metadata", {}) or {}
                files = metadata.get("files", []) or []

                # Build absolute file URLs
                file_urls: List[str] = []
                assets_base = f"https://archives.duc.tf/{year}"
                for fobj in files:
                    url_field = fobj.get("url") or fobj.get("path") or ""
                    if not url_field:
                        continue
                    if str(url_field).startswith("http"):
                        file_urls.append(str(url_field))
                    else:
                        file_urls.append(f"{assets_base}/{url_field.lstrip('/')}")

                extracted = ExtractedChallenge(
                    name=title,
                    description=description,
                    category=category,
                    difficulty=difficulty,
                    points=int(value) if isinstance(value, int) else None,
                    file_urls=file_urls,
                    source_url=url,
                    raw_html=None,
                    additional_context={
                        "author": None,
                        "flag_format": "DUCTF{.*}",
                        "additional_info": None,
                    },
                )

                success, download_stats = self._import_single_challenge(extracted, request, type("A", (), {"platform_name": f"DUCTF Archives {year}"}))
                if success:
                    result.total_files_downloaded += download_stats.get("files_downloaded", 0)
                    result.imported_challenges.append(extracted.name)
                    result.challenges_imported += 1
                    logger.info(f"Successfully imported {extracted.name} (DUCTF {year})")
                else:
                    result.failed_challenges.append({
                        "name": extracted.name,
                        "error": "Import processing failed"
                    })
                    result.challenges_failed += 1
            except Exception as e:
                logger.error(f"Failed to import DUCTF challenge: {e}")
                result.failed_challenges.append({
                    "name": c.get("title") or c.get("slug"),
                    "error": str(e)
                })
                result.challenges_failed += 1

        return True

    def _try_import_noctf_static(self, url: str, page_content: str, request: ImportRequest, result: ImportResult) -> bool:
        """Detect and import from generic NoCTF static export if available on the page.

        Looks for SvelteKit bootstrap that defines an assets base and tries `${assets}/export/challenges.json`.
        Returns True if handled.
        """
        import re
        from urllib.parse import urlparse, parse_qs

        # Heuristic: find `assets: "https://..."` in inline bootstrap
        m = re.search(r"assets:\s*\"([^\"]+)\"", page_content)
        if not m:
            return False
        assets_base = m.group(1).rstrip('/')
        export_base = f"{assets_base}/export"

        # Try to fetch export JSONs
        def _get_json(path: str) -> Optional[Dict[str, Any]]:
            try:
                resp = self.session.get(f"{export_base}/{path}", timeout=30)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.debug(f"NoCTF static: failed to fetch {export_base}/{path}: {e}")
                return None

        challenges_idx = _get_json("challenges.json")
        details_list = _get_json("challenge_details.json")
        if not challenges_idx or not isinstance(challenges_idx.get("data"), dict):
            return False
        if not details_list or not isinstance(details_list, list):
            return False

        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        slug_filter = (qs.get("c") or [None])[0]

        challenges = challenges_idx["data"].get("challenges", [])
        if slug_filter:
            challenges = [c for c in challenges if c.get("slug") == slug_filter]
        if request.max_challenges:
            challenges = challenges[: request.max_challenges]

        logger.info(f"NoCTF static: {len(challenges)} candidate challenge(s) from {export_base}")

        # Build map of details by id
        details_by_id: Dict[int, Dict[str, Any]] = {}
        for entry in details_list:
            try:
                cid = int(entry.get("data", {}).get("id"))
                details_by_id[cid] = entry
            except Exception:
                continue

        # Process each
        for c in challenges:
            try:
                cid = int(c.get("id"))
                title = c.get("title") or c.get("slug") or str(cid)
                value = c.get("value")
                tags = c.get("tags", {}) or {}
                category = (tags.get("categories") or "misc").lower()
                difficulty = (tags.get("difficulty") or "medium").lower()

                details = details_by_id.get(cid, {})
                data = details.get("data", {})
                description = data.get("description") or ""
                metadata = data.get("metadata", {}) or {}
                files = metadata.get("files", []) or []

                file_urls: List[str] = []
                assets_root = assets_base
                for fobj in files:
                    href = fobj.get("url") or fobj.get("path") or ""
                    if not href:
                        continue
                    if str(href).startswith("http"):
                        file_urls.append(str(href))
                    else:
                        file_urls.append(f"{assets_root}/{str(href).lstrip('/')}")

                extracted = ExtractedChallenge(
                    name=title,
                    description=description,
                    category=category,
                    difficulty=difficulty,
                    points=int(value) if isinstance(value, int) else None,
                    file_urls=file_urls,
                    source_url=url,
                    raw_html=None,
                    additional_context={
                        "author": None,
                        "flag_format": "{.*}",
                        "additional_info": None,
                    },
                )

                success, download_stats = self._import_single_challenge(extracted, request, type("A", (), {"platform_name": "NoCTF (static export)"}))
                if success:
                    result.total_files_downloaded += download_stats.get("files_downloaded", 0)
                    result.imported_challenges.append(extracted.name)
                    result.challenges_imported += 1
                    logger.info(f"Successfully imported {extracted.name} (NoCTF static)")
                else:
                    result.failed_challenges.append({
                        "name": extracted.name,
                        "error": "Import processing failed"
                    })
                    result.challenges_failed += 1
            except Exception as e:
                logger.error(f"Failed to import NoCTF static challenge: {e}")
                result.failed_challenges.append({
                    "name": c.get("title") or c.get("slug"),
                    "error": str(e)
                })
                result.challenges_failed += 1

        return True
    
    def _fetch_page_content(self, url: str, request: ImportRequest) -> Optional[str]:
        """Fetch page content with authentication if needed"""
        try:
            # Handle authentication
            if request.username and request.password:
                self.session.auth = (request.username, request.password)
            elif request.api_token:
                self.session.headers['Authorization'] = f'Bearer {request.api_token}'
            
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
            
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None
    
    def _handle_authentication(self, request: ImportRequest, analysis) -> bool:
        """Handle authentication if required"""
        # For now, assume auth details were provided in request
        # Could extend this to prompt for credentials interactively
        if analysis.requires_auth:
            return bool(request.username and request.password) or bool(request.api_token)
        return True
    
    def _passes_filters(self, challenge: ExtractedChallenge, request: ImportRequest) -> bool:
        """Check if challenge passes the specified filters"""
        # Name filter
        if request.challenge_filter:
            import re
            if not re.search(request.challenge_filter, challenge.name):
                return False
        
        # Category filter
        if request.category_filter and challenge.category:
            try:
                category = ChallengeCategory(challenge.category.lower())
                if category not in request.category_filter:
                    return False
            except ValueError:
                # Unknown category, let it pass if no specific filter
                pass
        
        return True
    
    def _import_single_challenge(self, extracted: ExtractedChallenge, request: ImportRequest, analysis) -> Tuple[bool, Dict[str, int]]:
        """Import a single challenge to the filesystem"""
        try:
            # Refine metadata using DSPy
            refined = self.pipeline.refine_metadata(extracted)
            
            # Create challenge directory
            challenge_name = self._sanitize_filename(refined["name"])
            challenge_dir = self.challenges_dir / challenge_name
            
            # Handle duplicate names
            counter = 1
            original_dir = challenge_dir
            while challenge_dir.exists():
                challenge_dir = original_dir.with_name(f"{original_dir.name}_{counter}")
                counter += 1
            
            challenge_dir.mkdir(parents=True)
            logger.info(f"Created challenge directory: {challenge_dir}")
            
            # Download files if requested
            downloaded_files = []
            if request.download_files and extracted.file_urls:
                downloaded_files = self.file_downloader.download_files(
                    extracted.file_urls,
                    challenge_dir,
                    max_file_size=request.max_file_size,
                    confirm=request.confirm_downloads
                )
            
            # Try to extract flag
            flag = None
            if extracted.flag:
                flag = extracted.flag
            else:
                # Try to extract flag from source page
                flag_format = extracted.additional_context.get("flag_format", "flag{.*}")
                flag = self.pipeline.extract_flag(
                    extracted.source_url or "", 
                    "", 
                    flag_format
                )
            
            # Create challenge.json (visible to agent)
            challenge_metadata = ChallengeMetadata(
                name=refined["name"],
                description=refined["description"],
                category=ChallengeCategory(refined["category"]),
                difficulty=DifficultyLevel(refined["difficulty"]),
                source_url=extracted.source_url,
                source_platform=analysis.platform_name,
                author=extracted.additional_context.get("author"),
                flag_format=extracted.additional_context.get("flag_format", "flag{.*}"),
                points=extracted.points,
                tags=refined["tags"],
                estimated_solve_time=refined["estimated_solve_time"],
                prerequisites=refined["prerequisites"],
                include_files=[f.name for f in downloaded_files] if downloaded_files else []
            )
            
            challenge_json_path = challenge_dir / "challenge.json"
            with open(challenge_json_path, 'w') as f:
                json.dump(challenge_metadata.dict(), f, indent=2, default=str)
            
            # Create solution.json (never copied to container)
            if flag:
                solution_data = ChallengeSolution(
                    challenge_name=refined["name"],
                    flag=flag,
                    source_url=extracted.source_url,
                    solution_approach=extracted.additional_context.get("additional_info")
                )
                
                solution_json_path = challenge_dir / "solution.json"
                with open(solution_json_path, 'w') as f:
                    json.dump(solution_data.dict(), f, indent=2, default=str)
            
            return True, {'files_downloaded': len(downloaded_files)}
            
        except Exception as e:
            logger.error(f"Failed to import challenge {extracted.name}: {e}")
            return False, {'files_downloaded': 0}
    
    def _sanitize_filename(self, name: str) -> str:
        """Sanitize challenge name for use as directory name"""
        # Remove/replace problematic characters
        import re
        sanitized = re.sub(r'[^\w\-_.]', '_', name)
        sanitized = re.sub(r'_+', '_', sanitized)  # Collapse multiple underscores
        return sanitized.strip('_').lower()[:50]  # Limit length