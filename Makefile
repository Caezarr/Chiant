.PHONY: install dev zones capture detect run prepare format lint clean

install:
	uv sync

dev:
	uv sync --dev

zones:
	uv run python scripts/download_lille_zones.py

prepare:
	uv run python scripts/prepare_dataset.py

capture:
	uv run boring capture

detect:
	uv run boring detect --source webcam

run:
	uv run boring run

format:
	uv run ruff format src scripts

lint:
	uv run ruff check src scripts

clean:
	rm -rf frames/ runs/ src/boring/__pycache__ src/boring/payment/__pycache__ .ruff_cache
