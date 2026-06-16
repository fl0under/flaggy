.PHONY: setup test scope prompt lab

setup:
	uv sync

test:
	uv run pytest -q

scope:
	uv run bbctl scope-check configs/scope.example.yaml

prompt:
	uv run bbctl prompt tasks/example.local.yaml

lab:
	uv run python benchmarks/local-toy-web/app.py
