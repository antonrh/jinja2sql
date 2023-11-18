.PHONY: help lint fmt
.DEFAULT_GOAL := help

help:
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

lint: ## Run code linters
	poetry run ruff check jinja2sql/ tests/
	poetry run mypy jinja2sql/ tests/

fmt: ## Run code formatters
	poetry run ruff format jinja2sql/ tests/

test:  ## Run unit tests
	poetry run pytest -vv --cov=jinja2sql/
