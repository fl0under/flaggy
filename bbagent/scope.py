from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
import ipaddress
import socket
import yaml


class ScopeError(ValueError):
    pass


VALID_KINDS = {"web", "binary", "host"}


@dataclass(frozen=True)
class Target:
    name: str
    kind: str = "web"
    base_url: str = ""
    path: str = ""
    host: str = ""
    port: int | None = None
    notes: str = ""
    max_rate_per_minute: int | None = None

    def locator(self) -> str:
        """Human-readable identifier for the target regardless of kind."""
        if self.kind == "web":
            return self.base_url
        if self.kind == "binary":
            return self.path
        if self.kind == "host":
            return f"{self.host}:{self.port}" if self.port else self.host
        return self.base_url or self.path or self.host

    def validate(self) -> None:
        if self.kind not in VALID_KINDS:
            raise ScopeError(
                f"Target {self.name} has unknown kind {self.kind!r} (use web|binary|host)."
            )
        if self.kind == "web":
            parsed = urlparse(self.base_url)
            if parsed.scheme not in {"http", "https"}:
                raise ScopeError(f"Web target {self.name} must be http(s): {self.base_url!r}")
            if not parsed.hostname:
                raise ScopeError(f"Web target {self.name} has no hostname: {self.base_url!r}")
        elif self.kind == "binary":
            if not self.path:
                raise ScopeError(f"Binary target {self.name} must set 'path'.")
        elif self.kind == "host":
            if not self.host:
                raise ScopeError(f"Host target {self.name} must set 'host'.")
            if self.port is None or not (1 <= self.port <= 65535):
                raise ScopeError(f"Host target {self.name} must set a valid 'port' (1-65535).")


@dataclass(frozen=True)
class Scope:
    path: Path
    program: str
    mode: str
    policy_url: str | None
    allowed_targets: list[Target]
    allowed_networks: list[str]
    forbidden_actions: list[str]
    out_dir: str
    evidence_dir: str

    @classmethod
    def load(cls, path: str | Path) -> "Scope":
        p = Path(path).expanduser().resolve()
        if not p.exists():
            raise ScopeError(f"Scope file not found: {p}")
        raw = yaml.safe_load(p.read_text()) or {}
        targets = [Target(**item) for item in raw.get("allowed_targets", [])]
        reporting = raw.get("reporting", {}) or {}
        scope = cls(
            path=p,
            program=raw.get("program", "unnamed"),
            mode=raw.get("mode", "unspecified"),
            policy_url=raw.get("policy_url"),
            allowed_targets=targets,
            allowed_networks=raw.get("allowed_networks", []),
            forbidden_actions=raw.get("forbidden_actions", []),
            out_dir=reporting.get("out_dir", "runs"),
            evidence_dir=reporting.get("evidence_dir", "evidence"),
        )
        scope.validate()
        return scope

    def validate(self) -> None:
        if not self.allowed_targets:
            raise ScopeError("Scope must contain at least one allowed target.")
        for target in self.allowed_targets:
            target.validate()
            if target.kind == "web":
                self.assert_url_allowed(target.base_url)

    def target(self, name: str) -> Target:
        for target in self.allowed_targets:
            if target.name == name:
                return target
        raise ScopeError(f"Unknown target '{name}'. Allowed: {', '.join(t.name for t in self.allowed_targets)}")

    def _host_in_allowed_networks(self, host: str) -> bool:
        if host in self.allowed_networks:
            return True
        try:
            infos = socket.getaddrinfo(host, None)
            ips = {ipaddress.ip_address(info[4][0]) for info in infos}
        except Exception as exc:
            raise ScopeError(f"Could not resolve host '{host}' while enforcing scope: {exc}") from exc
        for net in self.allowed_networks:
            try:
                network = ipaddress.ip_network(net, strict=False)
            except ValueError:
                continue
            if any(ip in network for ip in ips):
                return True
        return False

    def assert_url_allowed(self, url: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            raise ScopeError(f"URL has no host: {url}")

        for target in self.allowed_targets:
            if target.kind != "web":
                continue
            allowed = urlparse(target.base_url)
            if parsed.scheme == allowed.scheme and host == allowed.hostname:
                if not allowed.port or parsed.port in {allowed.port, None}:
                    return

        if self._host_in_allowed_networks(host):
            return

        allowed = ", ".join(t.locator() for t in self.allowed_targets)
        raise ScopeError(f"URL is outside scope: {url}. Allowed targets: {allowed}")

    def assert_host_allowed(self, host: str, port: int | None = None) -> None:
        for target in self.allowed_targets:
            if target.kind == "host" and target.host == host:
                if target.port is None or port is None or target.port == port:
                    return

        if self._host_in_allowed_networks(host):
            return

        allowed = ", ".join(t.locator() for t in self.allowed_targets)
        raise ScopeError(f"Host is outside scope: {host}:{port}. Allowed targets: {allowed}")

    def render_agent_brief(self, target_name: str | None = None) -> str:
        lines = [
            f"Program: {self.program}",
            f"Mode: {self.mode}",
            f"Policy URL: {self.policy_url or 'not provided'}",
            "Allowed targets:",
        ]
        for target in self.allowed_targets:
            marker = "*" if target_name and target.name == target_name else "-"
            rate = f", max {target.max_rate_per_minute}/min" if target.max_rate_per_minute else ""
            lines.append(f"  {marker} ({target.kind}) {target.name}: {target.locator()}{rate} — {target.notes}")
        lines.append("Forbidden actions: " + ", ".join(self.forbidden_actions))
        lines.append(
            "Operate only on the allowed targets. Stop before destructive, stealthy, high-volume, "
            "credential, persistence, or exfiltration activity."
        )
        return "\n".join(lines)
