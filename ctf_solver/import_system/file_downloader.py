"""
File downloader for challenge attachments
"""
import os
import requests
import logging
import hashlib
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin, urlparse


logger = logging.getLogger(__name__)


class FileDownloader:
    """
    Downloads challenge files with safety checks and validation
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Flaggy-CTF-Importer/1.0 (Educational Use)'
        })
        
        # Previously: extension whitelist. Relaxed to allow all extensions.
    
    def download_files(self, file_urls: List[str], destination_dir: Path, 
                      max_file_size: int = 100*1024*1024, confirm: bool = False) -> List[Path]:
        """
        Download files from URLs to destination directory
        Returns list of successfully downloaded file paths
        """
        downloaded_files = []
        
        # Show confirmation if requested
        if confirm and file_urls:
            print(f"\n📁 Found {len(file_urls)} files to download:")
            for i, url in enumerate(file_urls, 1):
                filename = url.split('/')[-1] or f"file_{i}"
                print(f"  {i}. {filename}")
                print(f"     URL: {url}")
            
            import click
            if not click.confirm(f"\nDownload these {len(file_urls)} files?"):
                logger.info("File download cancelled by user")
                return downloaded_files
        
        for url in file_urls:
            try:
                file_path = self._download_single_file(url, destination_dir, max_file_size)
                if file_path:
                    downloaded_files.append(file_path)
                    logger.info(f"Downloaded: {file_path.name}")
                else:
                    logger.warning(f"Failed to download: {url}")
                    
            except Exception as e:
                logger.error(f"Error downloading {url}: {e}")
        
        logger.info(f"Downloaded {len(downloaded_files)}/{len(file_urls)} files")
        return downloaded_files
    
    def _download_single_file(self, url: str, destination_dir: Path, 
                             max_file_size: int) -> Optional[Path]:
        """Download a single file with safety checks"""
        try:
            # Normalize common code hosting URLs to raw file URLs
            normalized_url = self._normalize_download_url(url)
            if normalized_url != url:
                logger.debug(f"Normalized URL: {url} -> {normalized_url}")
                url = normalized_url
            
            # Make HEAD request first to check file size and type
            head_response = self.session.head(url, timeout=10)
            
            # Check file size
            content_length = head_response.headers.get('content-length')
            if content_length and int(content_length) > max_file_size:
                logger.warning(f"File too large ({content_length} bytes): {url}")
                return None
            
            # Determine filename
            filename = self._extract_filename(url, head_response)
            if not filename:
                logger.warning(f"Could not determine filename for: {url}")
                return None
            
            # Safety check: ensure no path traversal; otherwise allow all extensions
            if not self._is_safe_filename(Path(filename), trust_dspy=True):
                logger.warning(f"Unsafe filename rejected: {filename}")
                return None
            
            file_path = destination_dir / filename
            
            # Download the file
            response = self.session.get(url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Write file with size limit enforcement
            total_size = 0
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        total_size += len(chunk)
                        if total_size > max_file_size:
                            logger.warning(f"File size limit exceeded during download: {url}")
                            file_path.unlink()  # Delete partial file
                            return None
                        f.write(chunk)
            
            # Make executable files executable
            if self._is_executable_file(file_path):
                file_path.chmod(file_path.stat().st_mode | 0o755)
            
            logger.debug(f"Downloaded {filename} ({total_size} bytes)")
            return file_path
            
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            return None
    
    def _normalize_download_url(self, url: str) -> str:
        """Convert code-hosting 'blob' links to 'raw' file URLs where possible."""
        try:
            from urllib.parse import urlparse, urlunparse
            pu = urlparse(url)
            host = pu.netloc.lower()
            path = pu.path
            # GitHub: /owner/repo/blob/<ref>/<path> -> /owner/repo/raw/<ref>/<path>
            if 'github.com' in host and '/blob/' in path:
                path = path.replace('/blob/', '/raw/')
                return urlunparse((pu.scheme, pu.netloc, path, pu.params, pu.query, pu.fragment))
            # GitLab: /owner/repo/-/blob/<ref>/<path> -> /owner/repo/-/raw/<ref>/<path>
            if 'gitlab.com' in host and '/-/blob/' in path:
                path = path.replace('/-/blob/', '/-/raw/')
                return urlunparse((pu.scheme, pu.netloc, path, pu.params, pu.query, pu.fragment))
        except Exception:
            pass
        return url

    def _extract_filename(self, url: str, response: requests.Response) -> Optional[str]:
        """Extract filename from URL or response headers"""
        # Try Content-Disposition header first
        content_disp = response.headers.get('content-disposition', '')
        if 'filename=' in content_disp:
            import re
            matches = re.search(r'filename[*]?=([^;]+)', content_disp)
            if matches:
                filename = matches.group(1).strip('\'"')
                return self._sanitize_filename(filename)
        
        # Fallback to URL path
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        
        if filename and '.' in filename:
            return self._sanitize_filename(filename)
        
        # Last resort: generate filename from URL hash
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return f"file_{url_hash}"
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem safety"""
        import re
        
        # Remove path separators and other dangerous characters
        filename = re.sub(r'[/\\:*?"<>|]', '_', filename)
        
        # Limit length
        name, ext = os.path.splitext(filename)
        if len(name) > 100:
            name = name[:100]
        
        return name + ext
    
    def _is_safe_filename(self, file_path: Path, trust_dspy: bool = True) -> bool:
        """Check if filename is safe (no path traversal). Extensions are allowed."""
        logger.debug(f"Checking file safety: {file_path}, trust_dspy={trust_dspy}")
        
        # Check for path traversal attempts  
        file_str = str(file_path)
        if '..' in file_str or file_str.startswith('/'):
            logger.debug(f"Path traversal rejected: {file_path} -> {file_str}")
            return False
        
        # Allow any extension (CTF workflows often require all kinds of files)
        return True
    
    def _is_executable_file(self, file_path: Path) -> bool:
        """Determine if file should be made executable"""
        executable_extensions = {'.bin', '.elf', '.exe'}
        
        # Check by extension
        if file_path.suffix.lower() in executable_extensions:
            return True
        
        # Check by filename (no extension executables)
        if not file_path.suffix:
            # Try to detect ELF files by magic bytes
            try:
                with open(file_path, 'rb') as f:
                    magic = f.read(4)
                    if magic == b'\x7fELF':  # ELF magic
                        return True
            except:
                pass
        
        return False