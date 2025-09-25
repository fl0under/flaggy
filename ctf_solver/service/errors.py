"""Service-layer exceptions."""


class ServiceError(RuntimeError):
    """Base error raised by the service client."""


class ServiceUnavailable(ServiceError):
    """Raised when the background service cannot be reached."""


class ServiceProtocolError(ServiceError):
    """Raised when a malformed response is received from the service."""


class ServiceTimeout(ServiceError):
    """Raised when an operation timed out waiting for the service."""


__all__ = [
    "ServiceError",
    "ServiceUnavailable",
    "ServiceProtocolError",
    "ServiceTimeout",
]


