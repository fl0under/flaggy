#!/usr/bin/env python3
"""
Main entry point for flaggy CTF solver
"""
import sys
import os
import json
import logging
import click
from typing import Optional
import time
import subprocess
from pathlib import Path

from ctf_solver.database.db import get_db_connection
from ctf_solver.core.orchestrator import SimpleOrchestrator
from ctf_solver.core.challenge_manager import ChallengeManager
from ctf_solver.optimization import DSPyGEPAOptimizer
from ctf_solver.import_system.cli import import_cli
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn


def setup_logging(debug: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


@click.group()
@click.option('--debug', is_flag=True, help='Enable debug logging')
@click.pass_context
def cli(ctx, debug):
    """Flaggy: LLM-powered CTF challenge solver"""
    setup_logging(debug)
    ctx.ensure_object(dict)
    ctx.obj['debug'] = debug


def _run_cmd(cmd):
    """Run a shell command and return (code, stdout, stderr)."""
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError as e:
        return 127, '', str(e)


def _docker_compose_up_postgres():
    """Start postgres service using docker compose (v2 or legacy)."""
    # Prefer v2 `docker compose`
    code, out, err = _run_cmd(["docker", "compose", "up", "-d", "postgres"])
    if code == 0:
        return True, out
    # Fallback to legacy docker-compose
    code2, out2, err2 = _run_cmd(["docker-compose", "up", "-d", "postgres"])
    if code2 == 0:
        return True, out2
    return False, err or err2


def _wait_for_postgres_health(container_name: str, timeout_seconds: int = 90):
    """Poll docker health status for a named container until healthy or timeout."""
    end_time = time.time() + timeout_seconds
    last_status = "unknown"
    while time.time() < end_time:
        code, out, err = _run_cmd(["docker", "inspect", "-f", "{{.State.Health.Status}}", container_name])
        if code == 0:
            status = (out or '').strip()
            last_status = status or last_status
            if status == 'healthy':
                return True
        time.sleep(2)
    return False


def _write_env_file(project_root: Path, api_key: str = '', force: bool = False):
    """Create or update a .env file at repo root with sane defaults."""
    env_path = project_root / '.env'
    if env_path.exists() and not force:
        return False, str(env_path)
    # Minimal content aligned with ctf_solver.config expectations
    lines = [
        'CTF_DSN="host=localhost port=5432 dbname=ctf user=flaggy password=flaggy123 sslmode=disable"',
        f'OPENROUTER_API_KEY="{api_key}"' if api_key else 'OPENROUTER_API_KEY=""',
        'CTF_MODEL="anthropic/claude-3.5-sonnet"',
        ''
    ]
    env_path.write_text("\n".join(lines))
    return True, str(env_path)


def _setup_database(reset: bool = False):
    """Create DB schema (optionally drop first)."""
    try:
        schema_path = Path(__file__).parent.parent / 'database' / 'schema.sql'
        schema_sql = schema_path.read_text()
        conn = get_db_connection()
        conn.autocommit = True
        cur = conn.cursor()
        if reset:
            drop_sql = (
                "DROP TABLE IF EXISTS steps CASCADE;"
                "DROP TABLE IF EXISTS attempts CASCADE;"
                "DROP TABLE IF EXISTS challenges CASCADE;"
            )
            cur.execute(drop_sql)
        cur.execute(schema_sql)
        cur.close()
        conn.close()
        return True, "schema applied"
    except Exception as e:
        return False, str(e)


def _sync_challenges():
    try:
        manager = ChallengeManager()
        manager.sync_challenges_to_db()
        return True, "challenges synced"
    except Exception as e:
        return False, str(e)


def _pull_exegol_image():
    image = "nwodtuhs/exegol:free"
    code, out, err = _run_cmd(["docker", "pull", image])
    if code == 0:
        return True, image
    return False, err or out


@cli.command()
@click.option('--api-key', default='', help='OpenRouter API key to write into .env')
@click.option('--force-env', is_flag=True, help='Overwrite existing .env if present')
@click.option('--reset', is_flag=True, help='Drop existing DB tables before creating schema')
@click.option('--skip-challenges', is_flag=True, help='Skip syncing challenges during init')
@click.option('--skip-pull', is_flag=True, help='Skip pulling Exegol image')
@click.pass_context
def init(ctx, api_key: str, force_env: bool, reset: bool, skip_challenges: bool, skip_pull: bool):
    """One-step setup: start DB, create .env, init schema, sync challenges, pull images."""
    try:
        click.echo("🚀 Starting Flaggy initialization\n")

        # 1) Bring up Postgres
        click.echo("📦 Bringing up PostgreSQL (Docker Compose)...")
        ok, msg = _docker_compose_up_postgres()
        if not ok:
            click.echo(f"❌ Failed to start postgres: {msg}", err=True)
            sys.exit(1)
        click.echo("   ▶ Waiting for database health (up to 90s)...")
        healthy = _wait_for_postgres_health("flaggy-postgres", timeout_seconds=90)
        if not healthy:
            click.echo("❌ Postgres did not become healthy in time", err=True)
            sys.exit(1)
        click.echo("   ✅ Postgres is healthy")

        # 2) Create .env
        project_root = Path(__file__).resolve().parents[2]
        created, path_str = _write_env_file(project_root, api_key=api_key, force=force_env)
        if created:
            click.echo(f"📝 Created .env at {path_str}")
        else:
            click.echo(f"📝 .env already exists at {path_str} (use --force-env to overwrite)")

        # 3) Initialize DB schema
        click.echo("🗄️  Initializing database schema...")
        ok, msg = _setup_database(reset=reset)
        if not ok:
            click.echo(f"❌ DB schema setup failed: {msg}", err=True)
            sys.exit(1)
        click.echo("   ✅ Database ready")

        # 4) Sync challenges (optional)
        if not skip_challenges:
            click.echo("🧩 Syncing challenges from ./challenges ...")
            ok, msg = _sync_challenges()
            if not ok:
                click.echo(f"⚠️  Challenge sync failed: {msg}")
            else:
                click.echo("   ✅ Challenges synchronized")
        else:
            click.echo("⏭️  Skipping challenge sync")

        # 5) Pull Exegol image (optional)
        if not skip_pull:
            click.echo("🐳 Pulling Exegol image (first time can be large)...")
            ok, msg = _pull_exegol_image()
            if ok:
                click.echo(f"   ✅ Pulled {msg}")
            else:
                click.echo(f"⚠️  Could not pull Exegol image automatically: {msg}")
        else:
            click.echo("⏭️  Skipping Exegol image pull")

        click.echo("\n✅ Initialization complete!")
        click.echo("Next steps:")
        click.echo("  • List challenges: uv run flaggy list-challenges")
        click.echo("  • Run TUI:         uv run flaggy-tui")
        click.echo("  • Solve a challenge: uv run flaggy solve 1")

    except Exception as e:
        click.echo(f"❌ Init failed: {e}", err=True)
        sys.exit(1)

@cli.command()
@click.argument('challenge_id', type=int)
@click.option('--max-parallel', default=1, help='Maximum parallel attempts')
@click.option('--optimized', help='Use optimized agent (specify name, default: "default")')
@click.pass_context
def solve(ctx, challenge_id: int, max_parallel: int, optimized: str):
    """Solve a specific challenge"""
    try:
        db = get_db_connection()
        
        # Handle optimized agent name
        agent_name = None
        if optimized:
            agent_name = optimized if optimized != "default" else "default"
            click.echo(f"🧠 Using optimized agent: {agent_name}")
        
        orchestrator = SimpleOrchestrator(
            db, 
            max_parallel=max_parallel,
            optimized_agent_name=agent_name
        )
        
        click.echo(f"Starting solver for challenge {challenge_id}")
        orchestrator.submit_challenge(challenge_id)
        
        # Wait for the single challenge to complete, then exit
        try:
            import time
            while not orchestrator.job_queue.empty() or orchestrator.active_runners:
                time.sleep(0.1)  # Check more frequently
        except KeyboardInterrupt:
            click.echo("\nStopping solver...")
        finally:
            # Clean shutdown after completion
            orchestrator.shutdown()
            
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command('list-attempts')
@click.option('--successful', is_flag=True, help='Show only successful attempts')
@click.option('--limit', default=20, help='Maximum attempts to show')
@click.option('--verbose', is_flag=True, help='Show detailed step information')
@click.pass_context
def list_attempts(ctx, successful: bool, limit: int, verbose: bool):
    """List previous challenge attempts for training analysis"""
    try:
        db = get_db_connection()
        cursor = db.cursor()
        
        # Base query
        where_clause = "WHERE status = 'completed'" if successful else ""
        query = f"""
            SELECT a.id, a.challenge_id, c.name, a.status, a.flag, a.total_steps, 
                   a.started_at, a.completed_at, 
                   EXTRACT(EPOCH FROM (a.completed_at - a.started_at)) as duration_seconds
            FROM attempts a
            JOIN challenges c ON a.challenge_id = c.id
            {where_clause}
            ORDER BY a.started_at DESC
            LIMIT %s
        """
        
        cursor.execute(query, (limit,))
        attempts = cursor.fetchall()
        
        if not attempts:
            click.echo("No attempts found.")
            return
            
        # Display summary
        total_attempts = len(attempts)
        successful_count = sum(1 for a in attempts if a[3] == 'completed')
        click.echo(f"\n📊 Found {total_attempts} attempts ({successful_count} successful)")
        click.echo("=" * 80)
        
        for attempt in attempts:
            attempt_id, challenge_id, name, status, flag, steps, started, completed, duration = attempt
            
            # Format status
            status_icon = "✅" if status == 'completed' else "❌"
            status_color = "green" if status == 'completed' else "red"
            
            # Format duration
            if duration:
                duration_str = f"{int(duration)}s"
            else:
                duration_str = "N/A"
                
            click.echo(f"{status_icon} Attempt {attempt_id} | {name} | {steps} steps | {duration_str}")
            
            if verbose and status == 'completed':
                # Show flag
                click.echo(f"   🏁 Flag: {flag}")
                
                # Show key steps
                cursor.execute("""
                    SELECT step_num, action, output, exit_code
                    FROM steps 
                    WHERE attempt_id = %s 
                    ORDER BY step_num DESC 
                    LIMIT 3
                """, (attempt_id,))
                
                steps_data = cursor.fetchall()
                if steps_data:
                    click.echo("   🔧 Final steps:")
                    for step_num, action, output, exit_code in steps_data:
                        try:
                            action_dict = json.loads(action) if action else {}
                            cmd = action_dict.get('cmd', str(action))[:60]
                            click.echo(f"      {step_num}: {cmd}...")
                        except:
                            click.echo(f"      {step_num}: {str(action)[:60]}...")
            
            click.echo()
            
        # Show training data summary
        if successful:
            click.echo(f"💡 These {successful_count} successful attempts can be used for DSPy optimization")
            click.echo("   Run 'flaggy optimize' to create a trained agent")
            
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--min-attempts', default=3, help='Minimum successful attempts required')
@click.option('--method', default='bootstrap', type=click.Choice(['bootstrap', 'mipro']), help='Optimization method')
@click.option('--max-demos', default=8, help='Maximum demonstrations to use')
@click.option('--name', default='default', help='Name for the optimized agent')
@click.pass_context
def optimize(ctx, min_attempts: int, method: str, max_demos: int, name: str):
    """Create optimized agent from successful attempts"""
    try:
        from ctf_solver.optimization import BatchOptimizer
        
        optimizer = BatchOptimizer()
        
        click.echo("🔍 Extracting training data from successful attempts...")
        training_data = optimizer.get_training_data(min_attempts=min_attempts)
        
        if len(training_data) < min_attempts:
            click.echo(f"❌ Not enough training data. Found {len(training_data)}, need {min_attempts}")
            click.echo("   Solve more challenges first, then run optimization.")
            sys.exit(1)
        
        click.echo(f"✅ Found {len(training_data)} training examples")
        click.echo(f"🧠 Starting {method} optimization with max {max_demos} demos...")
        
        # Run optimization
        optimized_agent = optimizer.optimize_agent(
            training_data, 
            method=method, 
            max_demos=max_demos
        )
        
        click.echo("💾 Saving optimized agent...")
        model_path = optimizer.save_optimized_agent(optimized_agent, name=name)
        
        click.echo(f"🎉 Optimization complete!")
        click.echo(f"   Agent saved as: {name}")
        click.echo(f"   Path: {model_path}")
        click.echo(f"   Use: flaggy solve --optimized {name} <challenge_id>")
        
    except Exception as e:
        click.echo(f"❌ Optimization failed: {e}", err=True)
        import traceback
        if ctx.obj and ctx.obj.get('debug'):
            traceback.print_exc()
        sys.exit(1)


@cli.command('list-agents')
@click.pass_context
def list_agents(ctx):
    """List saved optimized agents"""
    try:
        from ctf_solver.optimization import BatchOptimizer
        
        optimizer = BatchOptimizer()
        agents = optimizer.list_saved_agents()
        
        if not agents:
            click.echo("No optimized agents found.")
            click.echo("Run 'flaggy optimize' to create one.")
            return
        
        click.echo(f"📋 Found {len(agents)} optimized agents:")
        click.echo("=" * 50)
        
        for agent in agents:
            click.echo(f"🤖 {agent['name']}")
            click.echo(f"   Format: {agent['format']}")
            click.echo(f"   Demos: {agent.get('demo_count', 0)}")
            click.echo(f"   Optimized: {'✅' if agent.get('has_optimization', False) else '❌'}")
            click.echo(f"   Path: {agent['path']}")
            click.echo()
        
        click.echo("💡 Use: flaggy solve --optimized <name> <challenge_id>")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command('inspect-agent')
@click.argument('agent_name', default='default')
@click.pass_context
def inspect_agent(ctx, agent_name: str):
    """Inspect the contents of an optimized agent"""
    try:
        from ctf_solver.optimization import BatchOptimizer
        
        optimizer = BatchOptimizer()
        agent = optimizer.load_optimized_agent(agent_name)
        
        if not agent:
            click.echo(f"❌ Agent '{agent_name}' not found")
            click.echo("Run 'flaggy list-agents' to see available agents.")
            return
        
        click.echo(f"🔍 Agent: {agent_name}")
        click.echo("=" * 60)
        
        # Get demo information
        demo_count = 0
        demos = []
        if hasattr(agent, 'react') and hasattr(agent.react, 'predict'):
            demos = getattr(agent.react.predict, 'demos', [])
            demo_count = len(demos)
        
        click.echo(f"📄 Type: DSPy Optimized CTF Agent")
        # Show path to instruction artifact if present
        try:
            from ctf_solver.optimization import BatchOptimizer
            bo = BatchOptimizer()
            base_path = os.path.join(os.path.dirname(__file__), '..', 'optimization', 'artifacts', agent_name)
            instruction_path = os.path.abspath(os.path.join(base_path, 'instruction.json'))
            if os.path.exists(instruction_path):
                click.echo(f"📁 Path: {instruction_path}")
            else:
                click.echo(f"📁 Path: <artifact not found>")
        except Exception:
            click.echo(f"📁 Path: <unavailable>")
        click.echo(f"🎯 Demonstration Examples: {demo_count}")
        click.echo()
        
        if demo_count > 0:
            click.echo("✅ This agent contains optimized few-shot examples")
            click.echo("   It will use successful patterns from your training data")
            click.echo()
            
            # Show first few demo summaries
            click.echo("📋 Demo Patterns:")
            for i, demo in enumerate(demos[:5]):
                demo_str = str(demo)
                if 'file vuln' in demo_str and 'checksec' in demo_str:
                    click.echo(f"   • Demo {i+1}: Binary analysis workflow (file, checksec, strings, readelf)")
                elif 'ls -la' in demo_str:
                    click.echo(f"   • Demo {i+1}: Directory exploration and file inspection") 
                elif 'echo' in demo_str and 'read TARGET' in demo_str:
                    click.echo(f"   • Demo {i+1}: Interactive target selection workflow")
                elif 'Available binary_analysis tools' in demo_str:
                    click.echo(f"   • Demo {i+1}: Tool discovery and binary analysis")
                elif 'vulnerable.py' in demo_str:
                    click.echo(f"   • Demo {i+1}: Python script analysis")
                else:
                    click.echo(f"   • Demo {i+1}: {demo_str[:60]}...")
            
            if demo_count > 5:
                click.echo(f"   ... and {demo_count - 5} more demos")
        else:
            click.echo("⚠️  This agent has no few-shot examples")
            click.echo("   Optimization may have failed or no successful patterns were found")
        
    except Exception as e:
        click.echo(f"❌ Error inspecting agent: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--max-parallel', default=2, help='Maximum parallel attempts')
@click.pass_context  
def daemon(ctx, max_parallel: int):
    """Run flaggy as a daemon, processing challenges from queue"""
    try:
        db = get_db_connection()
        orchestrator = SimpleOrchestrator(db, max_parallel=max_parallel)
        
        click.echo(f"Starting flaggy daemon with {max_parallel} parallel workers")
        click.echo("Press Ctrl+C to stop")
        
        # Keep running until user interrupts
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            click.echo("\nStopping daemon...")
            
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('name')
@click.argument('binary_path')
@click.option('--flag-format', default='picoCTF{.*}', help='Flag format regex')
@click.option('--description', help='Challenge description')
@click.option('--category', help='Challenge category')
@click.pass_context
def add_challenge(ctx, name: str, binary_path: str, flag_format: str, 
                  description: Optional[str], category: Optional[str]):
    """Add a new challenge to solve"""
    try:
        db = get_db_connection()
        cursor = db.cursor()
        
        cursor.execute("""
            INSERT INTO challenges (name, binary_path, flag_format, description, category)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (name, binary_path, flag_format, description, category))
        
        challenge_id = cursor.fetchone()[0]
        db.commit()
        
        click.echo(f"Added challenge '{name}' with ID {challenge_id}")
        
    except Exception as e:
        click.echo(f"Error adding challenge: {e}", err=True)
        sys.exit(1)
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'db' in locals():
            db.close()


@cli.command()
@click.pass_context
def sync_challenges(ctx):
    """Scan challenges directory and sync to database"""
    try:
        manager = ChallengeManager()
        manager.sync_challenges_to_db()
        click.echo("Challenges synchronized with database")
    except Exception as e:
        click.echo(f"Error syncing challenges: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def list_challenges(ctx):
    """List all challenges"""
    try:
        db = get_db_connection()
        cursor = db.cursor()
        
        cursor.execute("""
            SELECT id, name, category, binary_path, flag_format, created_at
            FROM challenges
            ORDER BY created_at DESC
        """)
        
        challenges = cursor.fetchall()
        
        if not challenges:
            click.echo("No challenges found.")
            return
            
        click.echo("\nChallenges:")
        click.echo("-" * 80)
        for row in challenges:
            id_, name, category, binary_path, flag_format, created_at = row
            category_str = f"[{category}]" if category else ""
            click.echo(f"{id_:3d} | {name:20s} {category_str:15s} | {binary_path}")
        
    except Exception as e:
        click.echo(f"Error listing challenges: {e}", err=True)
        sys.exit(1)
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'db' in locals():
            db.close()


@cli.command()
@click.argument('challenge_id', type=int)
@click.pass_context
def test_mount(ctx, challenge_id: int):
    """Test container mounting for a challenge without running LLM agent"""
    try:
        from ctf_solver.core.challenge_manager import ChallengeManager
        from ctf_solver.containers.exegol import ExegolContainer
        
        db = get_db_connection()
        manager = ChallengeManager()
        
        click.echo(f"🔧 Testing container mounting for challenge {challenge_id}")
        
        # Create a test attempt record
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO attempts (challenge_id, status, started_at)
            VALUES (%s, 'running', NOW())
            RETURNING id
        """, (challenge_id,))
        attempt_id = cursor.fetchone()[0]
        db.commit()
        
        container_name = f"test_mount_{challenge_id}_{attempt_id}"
        click.echo(f"📦 Container: {container_name}")
        
        # Prepare workspace
        work_dir, container_mounts = manager.prepare_attempt_workspace(challenge_id, attempt_id)
        click.echo(f"📁 Workspace: {work_dir}")
        click.echo(f"🔗 Mounts: {container_mounts}")
        
        # Create container with mounts
        container = ExegolContainer(container_name, mounts=container_mounts)
        
        if container.start():
            click.echo("✅ Container started successfully")
            
            # Test mounting by running ls commands
            click.echo("\n🔍 Testing mounted directories:")
            
            # Check /challenge
            result = container.execute({'cmd': 'ls -la /challenge', 'tool': 'bash'})
            click.echo(f"📋 /challenge contents:")
            click.echo(result.get('stdout', 'No output'))
            
            # Check /challenge/original if mounted
            if '/challenge/original' in container_mounts.values():
                result = container.execute({'cmd': 'ls -la /challenge/original', 'tool': 'bash'})
                click.echo(f"📋 /challenge/original contents:")
                click.echo(result.get('stdout', 'No output'))
            
            # Show available tools
            tools = container.get_available_tools()
            total_tools = sum(len(t) for t in tools.values())
            click.echo(f"\n🛠️  Available tools: {total_tools} across {len(tools)} categories")
            
            # Cleanup
            container.stop()
            click.echo("🛑 Container stopped")
        else:
            click.echo("❌ Failed to start container")
            
        # Mark test attempt as completed
        cursor.execute("""
            UPDATE attempts SET status = 'completed', completed_at = NOW()
            WHERE id = %s
        """, (attempt_id,))
        db.commit()
        
    except Exception as e:
        click.echo(f"Error testing mount: {e}", err=True)
        sys.exit(1)
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'db' in locals():
            db.close()


## Legacy `gepa-optimize` command removed in favor of `dspy-gepa-optimize`.


# Add import commands
cli.add_command(import_cli)


@cli.command('dspy-gepa-optimize')
@click.option('--train', required=True, help='Comma-separated training challenge IDs, e.g. 1,2,3')
@click.option('--dev', default='', help='Comma-separated dev challenge IDs, optional')
@click.option('--name', default='', help='Name to save the best instruction artifact under')
@click.option('--seed-instruction', default='', help='Seed instruction text override (optional)')
@click.option('--auto', default='none', type=click.Choice(['light','medium','heavy','none']), help='DSPy GEPA auto budget (use "none" when setting explicit budgets)')
@click.option('--max-full-evals', default=0, type=int, help='Max full evals (0 to disable)')
@click.option('--max-metric-calls', default=0, type=int, help='Max metric calls (0 to disable)')
@click.option('--seed', default=0, type=int, help='Random seed')
@click.option('--container-prefix', default='gepa', help='Container name prefix for optimization runs')
@click.option('--log-dir', default='', help='Directory for GEPA logs/checkpoints (enables save/resume)')
@click.pass_context
def dspy_gepa_optimize(ctx, train: str, dev: str, name: str, seed_instruction: str, auto: str, max_full_evals: int, max_metric_calls: int, seed: int, container_prefix: str, log_dir: str):
    """Run official DSPy GEPA optimizer (reflective prompt evolution)."""
    try:
        db = get_db_connection()

        def parse_ids(s: str):
            s = (s or '').strip()
            if not s:
                return []
            return [int(x) for x in s.split(',') if x.strip().isdigit()]

        train_ids = parse_ids(train)
        dev_ids = parse_ids(dev)
        if not train_ids:
            click.echo('❌ No training challenge IDs provided', err=True)
            sys.exit(1)

        # Map CLI params to DSPy GEPA
        auto_val = None if auto == 'none' else auto
        mfe = max_full_evals if max_full_evals and max_full_evals > 0 else None
        mmc = max_metric_calls if max_metric_calls and max_metric_calls > 0 else None

        # If explicit budgets are set, ignore auto to satisfy GEPA's exclusivity
        if mfe is not None or mmc is not None:
            auto_val = None

        # Validate exactly one of (auto, max_full_evals, max_metric_calls)
        selected = [v for v in [auto_val, mfe, mmc] if v is not None]
        if len(selected) != 1:
            click.echo('❌ Exactly one of --auto, --max-full-evals, --max-metric-calls must be set', err=True)
            sys.exit(1)

        click.echo(f"🤖 Starting DSPy GEPA optimization")
        click.echo(f"   Train IDs: {train_ids}")
        if dev_ids:
            click.echo(f"   Dev IDs:   {dev_ids}")
        click.echo(f"   auto={auto_val}  max_full_evals={mfe}  max_metric_calls={mmc}")
        if name:
            click.echo(f"   Artifact name: {name}")
        if seed_instruction:
            click.echo("   Using custom seed instruction")
        if log_dir:
            click.echo(f"   Log dir: {log_dir}")

        optimizer = DSPyGEPAOptimizer(db, container_name_prefix=container_prefix)

        # Progress bar pinned at bottom; logs scroll above
        with Progress(
            TextColumn("[bold blue]GEPA[/]"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TextColumn("ETA"),
            TimeRemainingColumn(),
            transient=False,
        ) as progress:
            total_examples = len(train_ids) + (len(dev_ids) if dev_ids else 0)
            task = progress.add_task("opt", total=total_examples if total_examples > 0 else 1)

            def progress_cb(ev):
                try:
                    if isinstance(ev, dict) and ev.get("type") == "metric":
                        progress.advance(task, 1)
                except Exception:
                    pass

            result = optimizer.run(
                train_ids=train_ids,
                dev_ids=dev_ids if dev_ids else None,
                name=name if name else None,
                seed_instruction=seed_instruction if seed_instruction else None,
                auto=auto_val,
                max_full_evals=mfe,
                max_metric_calls=mmc,
                random_seed=seed,
                progress_callback=progress_cb,
                log_dir=log_dir if log_dir else None,
            )

        click.echo("\n✅ DSPy GEPA optimization complete!")
        click.echo(f"   Saved artifact: {result['artifact_name']}")
        click.echo(f"   Path: {result['artifact_path']}")
        if result.get('log_dir'):
            click.echo(f"   Run logs: {result['log_dir']}")
        click.echo("\nRun with optimized prompts using:\n  flaggy solve --optimized " + result['artifact_name'] + " <challenge_id>")

    except Exception as e:
        click.echo(f"❌ DSPy GEPA optimization failed: {e}", err=True)
        import traceback
        if ctx.obj and ctx.obj.get('debug'):
            traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point"""
    cli()


if __name__ == '__main__':
    main()


