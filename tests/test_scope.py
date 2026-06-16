from pathlib import Path

import pytest

from bbagent.scope import Scope, ScopeError, Target
from bbagent.tasks import Task

ROOT = Path(__file__).resolve().parents[1]


def test_scope_loads_and_allows_local_target():
    scope = Scope.load(ROOT / "configs" / "scope.example.yaml")
    scope.assert_url_allowed("http://127.0.0.1:8080/echo?q=test")


def test_scope_rejects_outside_target():
    scope = Scope.load(ROOT / "configs" / "scope.example.yaml")
    with pytest.raises(ScopeError):
        scope.assert_url_allowed("https://example.com/")


def test_task_loads():
    task = Task.load(ROOT / "tasks" / "example.local.yaml")
    assert task.target == "toy-web"


def test_ctf_scope_has_binary_and_host_targets():
    scope = Scope.load(ROOT / "configs" / "scope.ctf.example.yaml")
    kinds = {t.name: t.kind for t in scope.allowed_targets}
    assert kinds["crackme"] == "binary"
    assert kinds["pwn-remote"] == "host"
    # In-scope host:port is allowed.
    scope.assert_host_allowed("127.0.0.1", 31337)


def test_ctf_scope_rejects_out_of_scope_host():
    scope = Scope.load(ROOT / "configs" / "scope.ctf.example.yaml")
    with pytest.raises(ScopeError):
        scope.assert_host_allowed("8.8.8.8", 53)


def test_binary_target_requires_path():
    with pytest.raises(ScopeError):
        Target(name="x", kind="binary").validate()


def test_unknown_target_kind_rejected():
    with pytest.raises(ScopeError):
        Target(name="x", kind="satellite", base_url="http://127.0.0.1").validate()


def test_ctf_task_loads():
    task = Task.load(ROOT / "tasks" / "example.ctf.yaml")
    assert task.target == "crackme"
    assert task.kind == "ctf"
