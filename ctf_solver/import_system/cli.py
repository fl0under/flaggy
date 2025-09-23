"""
Command-line interface for the challenge import system
"""
import click
import json
import logging
from pathlib import Path
from typing import Optional

from .schemas import ImportRequest, ChallengeCategory, DifficultyLevel
from .importer import ChallengeImporter


logger = logging.getLogger(__name__)


@click.group(name="import")
def import_cli():
    """Import challenges from various sources"""
    pass


@import_cli.command()
@click.argument("url")
@click.option("--username", "-u", help="Username for authentication")
@click.option("--password", "-p", help="Password for authentication") 
@click.option("--token", "-t", help="API token for authentication")
@click.option("--category", "-c", multiple=True, help="Filter by categories (can be used multiple times)")
@click.option("--filter", "-f", "name_filter", help="Regex filter for challenge names")
@click.option("--max", "-m", type=int, help="Maximum number of challenges to import")
@click.option("--no-files", is_flag=True, help="Don't download challenge files")
@click.option("--confirm-downloads", is_flag=True, help="Ask for confirmation before downloading files")
@click.option("--max-file-size", type=int, default=100*1024*1024, help="Maximum file size in bytes")
@click.option("--output-dir", "-o", help="Output directory for challenges")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
def url(url: str, username: Optional[str], password: Optional[str], token: Optional[str],
        category: tuple, name_filter: Optional[str], max: Optional[int], no_files: bool,
        confirm_downloads: bool, max_file_size: int, output_dir: Optional[str], verbose: bool):
    """Import challenges from a URL"""
    
    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Parse categories
    category_filter = []
    for cat in category:
        try:
            category_filter.append(ChallengeCategory(cat.lower()))
        except ValueError:
            click.echo(f"Warning: Unknown category '{cat}', ignoring")
    
    # Create import request
    request = ImportRequest(
        url=url,
        username=username,
        password=password,
        api_token=token,
        challenge_filter=name_filter,
        category_filter=category_filter,
        max_challenges=max,
        download_files=not no_files,
        confirm_downloads=confirm_downloads,
        max_file_size=max_file_size
    )
    
    # Initialize importer
    challenges_dir = output_dir or "/root/flaggy/challenges"
    importer = ChallengeImporter(challenges_dir)
    
    # Perform import
    click.echo(f"Importing challenges from: {url}")
    if category_filter:
        click.echo(f"Category filter: {[c.value for c in category_filter]}")
    if name_filter:
        click.echo(f"Name filter: {name_filter}")
    if max:
        click.echo(f"Max challenges: {max}")
    
    click.echo("Starting import...")
    result = importer.import_challenges(request)
    
    # Display results
    if result.success:
        click.echo(f"✅ Import completed successfully!")
        click.echo(f"   Imported: {result.challenges_imported} challenges")
        if result.challenges_failed > 0:
            click.echo(f"   Failed: {result.challenges_failed} challenges")
        click.echo(f"   Duration: {result.import_duration:.1f}s")
        
        if result.imported_challenges:
            click.echo(f"   Successfully imported:")
            for name in result.imported_challenges:
                click.echo(f"     - {name}")
        
        if result.failed_challenges:
            click.echo(f"   Failed challenges:")
            for failed in result.failed_challenges:
                click.echo(f"     - {failed.get('name', failed.get('url', 'unknown'))}: {failed['error']}")
    
    else:
        click.echo(f"❌ Import failed: {result.error_message}")
        if result.challenges_imported > 0:
            click.echo(f"   Partial success: {result.challenges_imported} challenges imported")


@import_cli.command()
@click.argument("challenge_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--name", "-n", help="Challenge name (default: directory name)")
@click.option("--category", "-c", help="Challenge category")
@click.option("--difficulty", "-d", help="Challenge difficulty")
@click.option("--description", help="Challenge description")
@click.option("--flag", help="Challenge flag")
@click.option("--points", type=int, help="Point value")
def local(challenge_dir: str, name: Optional[str], category: Optional[str],
          difficulty: Optional[str], description: Optional[str], flag: Optional[str],
          points: Optional[int]):
    """Import a challenge from a local directory"""
    
    challenge_path = Path(challenge_dir)
    challenge_name = name or challenge_path.name
    
    # Create basic metadata
    from .schemas import ChallengeMetadata, ChallengeSolution, ChallengeCategory, DifficultyLevel
    
    metadata = ChallengeMetadata(
        name=challenge_name,
        description=description or f"Challenge imported from {challenge_path}",
        category=ChallengeCategory(category.lower()) if category else ChallengeCategory.MISC,
        difficulty=DifficultyLevel(difficulty.lower()) if difficulty else DifficultyLevel.MEDIUM,
        points=points,
        # Include all files by default
        include_files=["*"]
    )
    
    # Copy to challenges directory
    import shutil
    dest_dir = Path("/root/flaggy/challenges") / challenge_name
    if dest_dir.exists():
        click.confirm(f"Challenge directory {dest_dir} already exists. Overwrite?", abort=True)
        shutil.rmtree(dest_dir)
    
    shutil.copytree(challenge_path, dest_dir)
    
    # Write metadata
    with open(dest_dir / "challenge.json", 'w') as f:
        json.dump(metadata.dict(), f, indent=2, default=str)
    
    # Write solution if flag provided
    if flag:
        solution = ChallengeSolution(
            challenge_name=challenge_name,
            flag=flag
        )
        with open(dest_dir / "solution.json", 'w') as f:
            json.dump(solution.dict(), f, indent=2, default=str)
    
    click.echo(f"✅ Successfully imported local challenge: {challenge_name}")


@import_cli.command() 
def list_categories():
    """List available challenge categories"""
    click.echo("Available categories:")
    for category in ChallengeCategory:
        click.echo(f"  - {category.value}")


@import_cli.command()
def list_difficulties():
    """List available difficulty levels"""
    click.echo("Available difficulties:")
    for difficulty in DifficultyLevel:
        click.echo(f"  - {difficulty.value}")


if __name__ == "__main__":
    import_cli()