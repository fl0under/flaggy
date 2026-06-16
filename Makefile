.PHONY: setup test scope prompt lab

setup:
	python -m pip install -e . pytest

test:
	pytest -q

scope:
	scripts/bbctl scope-check configs/scope.example.yaml

prompt:
	scripts/bbctl prompt tasks/example.local.yaml

lab:
	python benchmarks/local-toy-web/app.py
