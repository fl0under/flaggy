.PHONY: setup test check export lab

setup:
	uv sync

test:
	uv run pytest -q

check:
	uv run flaggy check configs/scope.example.yaml

export:
	uv run flaggy export tasks/example.local.yaml --force

lab:
	uv run python benchmarks/local-toy-web/app.py
