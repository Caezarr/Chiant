.PHONY: install dev zones capture detect run box-run box-doctor box-burn-in box-notify-test box-ready prepare scrape-baseline scrape-negatives import-openimages train vision-ready vision-eval vision-benchmark autopay-ready autopay-smoke mitmproxy test format lint clean

install:
	uv sync

dev:
	uv sync --dev

zones:
	uv run python scripts/download_lille_zones.py

prepare:
	uv run python scripts/prepare_dataset.py

scrape-baseline:
	uv run python scripts/scrape_baseline.py --profile positives

scrape-negatives:
	uv run python scripts/scrape_baseline.py --profile negatives

import-openimages:
	uv run python scripts/import_openimages_manifest.py --descriptions datasets/openimages/class-descriptions-boxable.csv --annotations datasets/openimages/train-annotations-bbox.csv

landing:
	@echo "Landing dispo localement → file://$(PWD)/docs/index.html"
	@open docs/index.html 2>/dev/null || echo "Ouvre docs/index.html dans ton navigateur."

capture:
	uv run boring capture

detect:
	uv run boring detect --source webcam

run:
	uv run boring run

box-run:
	uv run boring box-run

box-doctor:
	uv run boring box-doctor

box-burn-in:
	uv run boring box-burn-in --minutes 30 --interval 60 --output burn-in

box-notify-test:
	uv run boring box-notify-test

box-ready:
	uv run boring box-ready

contest:
	@echo "Exemple : uv run boring contest-fps --subject FPS-DEMO --reason 'J''avais payé via PayByPhone.'"
	@uv run boring contest-fps --subject "FPS-DEMO-001" --reason "Démo CLI" --amount 35

train:
	uv run python scripts/train_custom.py --data datasets/control_vehicle_v1/data.yaml

vision-ready:
	uv run boring vision-ready

vision-eval:
	uv run boring vision-eval

vision-benchmark:
	uv run boring vision-benchmark

autopay-ready:
	uv run boring autopay-ready

autopay-smoke:
	uv run boring autopay-smoke --yes

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
