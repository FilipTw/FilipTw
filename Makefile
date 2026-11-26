PY ?= .venv/bin/python

.PHONY: check check-linux fix

check:  ## lint, format, types and tests: the same checks CI runs
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .
	$(PY) -m mypy
	$(PY) -m pytest -q tests

fix:  ## apply ruff's safe fixes and formatting
	$(PY) -m ruff check --fix .
	$(PY) -m ruff format .

check-linux:  ## the same checks in CI's Python on Linux, which catches platform-dependent SVG output
	docker run --rm -v "$(CURDIR)":/src:ro python:3.12-slim sh -c \
	  'cp -r /src /w && cd /w && rm -rf .venv && pip install -q -r requirements-dev.txt >/dev/null 2>&1 && \
	   ruff check . && ruff format --check . && mypy && python -m pytest -q tests'
