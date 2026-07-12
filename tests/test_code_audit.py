from __future__ import annotations

from pathlib import Path

from boring.code_audit import run_code_audit


def test_code_audit_reports_big_files_stubs_and_missing_field_artifacts(tmp_path: Path):
    src = tmp_path / "src" / "boring"
    tests = tmp_path / "tests"
    src.mkdir(parents=True)
    tests.mkdir()
    (src / "small.py").write_text("print('ok')\n")
    (src / "large.py").write_text("x = 1\n" * 1001)
    (tests / "test_small.py").write_text("def test_ok():\n    assert True\n")

    report = run_code_audit(tmp_path)

    assert report.big_files == [("src/boring/large.py", 1001)]
    assert report.stub_providers == ["easypark", "flowbird", "opngo"]
    assert "models/best.pt" in report.missing_field_artifacts
    assert report.test_files == 1
    assert report.warning_count >= 1
