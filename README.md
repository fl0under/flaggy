# flaggy
a little LLM powered friend to find flags in CTFs

This project is in early stages! Documentation may not be updated and the code is evolving.

flaggy uses DSPy in a Chain of Thought (CoT) loop to solve capture the flag challenges.
It runs in a [Exegol](https://exegol.com/) docker container - it provides common tools for solving CTFs.

I recommend starting with gpt-5-mini or grok-4-fast as capable and cost effective models.

## Installation

### Prerequisites
- Python 3.9+
- [uv](https://github.com/astral-sh/uv) for Python package management
- Docker and Docker Compose for containers and database
- [Exegol wrapper](https://exegol.readthedocs.io/) for container management
- Internet connection for pulling Exegol image automatically

### Setup

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install Exegol wrapper**:
   ```bash
   # Install Exegol wrapper globally
   pip install exegol
   ```

3. **Clone and setup the project**:
   ```bash
   git clone https://github.com/fl0under/flaggy
   cd flaggy
   
   # Install Python dependencies (includes Exegol)
   uv sync
   ```

4. **One-step project init**:
   ```bash
   # This pulls Docker images, brings up Postgres (waits for healthy),
   # writes .env (optionally with your API key), creates schema, syncs challenges,
   # and pre-pulls the Exegol container image.
   uv run flaggy init --api-key "your-openrouter-api-key"
   ```

5. **Run TUI**:
   ```bash
   uv run flaggy-tui
   ```

## Quick Start

After setup, try solving a challenge:

```bash
# List available challenges
uv run flaggy list-challenges

# Solve the first challenge (service auto-starts if needed)
uv run flaggy solve 1

# Monitor progress in real-time (separate terminal)
uv run flaggy-tui
```

### Additional commands

- `uv run flaggy list-attempts [--successful] [--verbose]`
  - Shows previous runs; `--verbose` will print flags. Use with care.
- `uv run flaggy optimize [--min-attempts N] [--method bootstrap|mipro] [--max-demos N] [--name NAME]`
  - Creates an optimized agent from successful attempts.
- `uv run flaggy list-agents` / `uv run flaggy inspect-agent <name>`
  - Manage and inspect saved optimized agents.
- `uv run flaggy service start [--parallel N]`
  - Starts the shared background service (auto-starts when running `solve` or the TUI).
- `uv run flaggy service stop`
  - Stops the background service.
- `uv run flaggy test-mount <challenge_id>`
  - Verifies container mounting and tool availability without running the LLM.
- `uv run flaggy dspy-gepa-optimize --train 1,2,3 [--dev 4,5] [--auto light|medium|heavy|none] [...]`
  - Runs the official DSPy GEPA optimizer on selected challenges.

## Architecture

- **Agent**: DSPy-powered LLM agent using OpenRouter
- **Containers**: Exegol Docker containers for isolated execution
- **Database**: PostgreSQL for tracking challenges, attempts, and steps
- **TUI**: Textual-based terminal interface for monitoring
- **Orchestrator**: Python-based job queue and worker management

## TUI

Run with `uv run flaggy-tui`. Key bindings: `y` copies the current attempt's flag to the clipboard, `q` quits.

## Development

### Install dev dependencies
```bash
uv sync --group dev
```

### Run tests
```bash
uv run pytest
```

### Code formatting
```bash
uv run black ctf_solver/
uv run ruff check ctf_solver/
```

### Type checking
```bash
uv run mypy ctf_solver/
```

## Configuration

Environment variables:
- `CTF_DSN`: PostgreSQL connection string
- `OPENROUTER_API_KEY`: Required API key for OpenRouter
- `CTF_MODEL`: Model to use (default: anthropic/claude-3.5-sonnet)

Notes:
- `.env` is read from the project root when commands are run from that directory. If you run from elsewhere, set environment variables explicitly.
- Exegol image pulls can be large on first run; the initial setup may take several minutes.
- On WSL2, ensure Docker Desktop integration is enabled and port 5432 is accessible from Linux; use `docker compose ps` to confirm health.

Advanced init options:
- `uv run flaggy init --force-env` to overwrite an existing `.env`.
- `uv run flaggy init --reset` to drop and recreate DB tables.
- `uv run flaggy init --skip-challenges` to skip syncing `./challenges`.
- `uv run flaggy init --skip-pull` to skip pulling the Exegol image.

Security & privacy:
- You are running untrusted challenge binaries—keep them inside containers.
- Challenge data and outputs may be sent to LLM providers via OpenRouter. Avoid sending real competition flags or proprietary data.

Tested Python versions: 3.9–3.12

## License

MIT