# aiohttp responses

Mocking AIOHTTP Requests

Built on: Poetry, Docker, Python3

Authors: <br>
Chris Lee <chris@indico.io>

## Getting started

```bash
$ poetry install

# Test Installation
$ poetry run python3 -c "import aiohttp_responses; print(aiohttp_responses)"
```

## Running tests

```bash
$ poetry run test
```

## pre-commit hooks

Configured pre-commit hooks

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v2.3.0
    hooks:
      - id: check-yaml
      - id: end-of-file-fixer
      - id: trailing-whitespace
  - repo: https://github.com/pycqa/isort
    rev: 5.10.1
    hooks:
      - id: isort
        name: isort (python)
        args: ["--profile", "black"]
  - repo: https://github.com/psf/black
    rev: 22.3.0
    hooks:
      - id: black
```

Usage:

```bash
$ pre-commit install
# Example usage outside of git hooks
$ pre-commit run -a
```
