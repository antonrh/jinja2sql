.PHONY: help lint fmt
.DEFAULT_GOAL := help

help:
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

lint: ## Run code linters
	poetry run black jinjaq/ tests/ --check
	poetry run ruff check jinjaq/ tests/
	poetry run mypy jinjaq/ tests/

fmt: ## Run code formatters
	poetry run black jinjaq/ tests/
	poetry run ruff check jinjaq/ tests/ --fix

test:  ## Run unit tests
	poetry run pytest -vv tests/unit --cov=jinjaq/
