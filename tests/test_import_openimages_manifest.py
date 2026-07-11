from __future__ import annotations

import json
from pathlib import Path

from scripts.import_openimages_manifest import (
    iter_openimages_records,
    load_class_ids,
    load_manifest_image_ids,
    parse_class_names,
    write_download_list,
)


def test_load_class_ids_filters_requested_names(tmp_path: Path):
    descriptions = tmp_path / "class-descriptions-boxable.csv"
    descriptions.write_text("/m/car,Car\n/m/dog,Dog\n/m/bus,Bus\n")

    class_ids = load_class_ids(descriptions, ("Car", "Bus"))

    assert class_ids == {"/m/car": "Car", "/m/bus": "Bus"}


def test_iter_openimages_records_filters_classes_and_dedupes(tmp_path: Path):
    annotations = tmp_path / "train-annotations-bbox.csv"
    annotations.write_text(
        "ImageID,Source,LabelName,Confidence,XMin,XMax,YMin,YMax\n"
        "img-1,x,/m/car,1,0,1,0,1\n"
        "img-2,x,/m/dog,1,0,1,0,1\n"
        "img-3,x,/m/bus,1,0,1,0,1\n"
        "img-1,x,/m/car,1,0,1,0,1\n"
    )

    records = iter_openimages_records(
        annotations_csv=annotations,
        class_ids={"/m/car": "Car", "/m/bus": "Bus"},
        split="train",
        output_dir=tmp_path / "baseline",
        limit=10,
    )

    assert [record.image_id for record in records] == ["img-1", "img-3"]
    assert records[0].license_status == "open-images"
    assert records[0].license_reviewed is True
    assert records[0].profile == "negatives"
    assert records[0].label_hint == "hard_negative"
    assert records[0].url.endswith("/train/img-1.jpg")


def test_load_manifest_image_ids_ignores_bad_lines(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps({"image_id": "img-1"}) + "\nnot-json\n")

    assert load_manifest_image_ids(manifest) == {"img-1"}


def test_write_download_list(tmp_path: Path):
    annotations = tmp_path / "train-annotations-bbox.csv"
    annotations.write_text(
        "ImageID,Source,LabelName,Confidence,XMin,XMax,YMin,YMax\nimg-1,x,/m/car,1,0,1,0,1\n"
    )
    records = iter_openimages_records(
        annotations_csv=annotations,
        class_ids={"/m/car": "Car"},
        split="validation",
        output_dir=tmp_path / "baseline",
        limit=10,
    )

    output = tmp_path / "download-list.txt"
    write_download_list(output, records)

    assert output.read_text() == (
        "https://storage.googleapis.com/openimages/2018_04/validation/img-1.jpg\n"
    )


def test_parse_class_names_falls_back_to_defaults():
    assert parse_class_names(" Car, Bus ,,") == ("Car", "Bus")
    assert "Car" in parse_class_names("")
