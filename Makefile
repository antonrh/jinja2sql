.PHONY: help lint fmt test
.DEFAULT_GOAL := help

help:
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

lint: ## Run code linters
	uv run mypy jinja2sql tests
	uv run ruff check jinja2sql tests
	uv run ruff format jinja2sql tests --check

fmt: ## Run code formatters
	uv run ruff check jinja2sql tests --fix
	uv run ruff format jinja2sql tests

test:  ## Run unit tests
	uv run pytest -vv tests --cov=jinja2sql
