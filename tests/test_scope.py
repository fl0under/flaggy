from pathlib import Path

import pytest

from bbagent.scope import Scope, ScopeError
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
