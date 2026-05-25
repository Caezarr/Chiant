.PHONY: install dev zones capture detect run prepare train mitmproxy test format lint clean

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

train:
	uv run python scripts/train_custom.py --data datasets/control_vehicle_v1/data.yaml

mitmproxy:
	uv run mitmproxy -s scripts/paybyphone_capture.py

test:
	uv run pytest tests/ -v

format:
	uv run ruff format src scripts

lint:
	uv run ruff check src scripts

clean:
	rm -rf frames/ runs/ src/boring/__pycache__ src/boring/payment/__pycache__ .ruff_cache
