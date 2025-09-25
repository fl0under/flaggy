"""Constants shared between the flaggy service client and server."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_SOCKET_PATH = Path(os.environ.get("FLAGGY_SERVICE_SOCKET", "/tmp/flaggy-service.sock"))
DEFAULT_LOG_PATH = Path(os.environ.get("FLAGGY_SERVICE_LOG", "~/flaggy-service.log")).expanduser()
SERVICE_START_TIMEOUT = float(os.environ.get("FLAGGY_SERVICE_START_TIMEOUT", "20"))
SERVICE_STOP_TIMEOUT = float(os.environ.get("FLAGGY_SERVICE_STOP_TIMEOUT", "10"))


