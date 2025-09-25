# Flaggy Service Architecture

## Overview

Flaggy now relies on a single background service process to manage solving attempts. All front-ends (CLI, TUI, automation) talk to this service via a Unix domain socket.

## Startup

- The service binary is `python -m ctf_solver.service.server`.
- `ServiceSupervisor` ensures a socket exists and will spawn the service on demand.
- Socket path defaults to `/tmp/flaggy-service.sock` but can be overridden with `FLAGGY_SERVICE_SOCKET`.

## API

Messages are JSON framed with a 4-byte length prefix.

- `health`: returns status.
- `start_attempt`: queue a challenge solve, returns `attempt_id`.
- `cancel_attempt`: request cancellation.
- `get_attempt_status`: fetch latest status (running/completed/failed/cancelled) plus flag or metadata when available.
- `shutdown`: stop the service gracefully.

## Clients

- CLI uses `ServiceSupervisor` for `flaggy solve`, which waits on attempt completion.
- TUI challenges view uses the same supervisor for start/cancel actions and polls DB to render.

## Cancellation

`SimpleOrchestrator.request_cancel` signals the active `ChallengeRunner` to stop and shuts down containers. The service marks attempts cancelled once `ChallengeRunner` acknowledges.

## Tips

- Use `uv run flaggy service start` to preload the service or adjust defaults.
- `uv run flaggy service stop` sends a `shutdown` action.
- Set `FLAGGY_SERVICE_SOCKET` to run multiple environments concurrently.
