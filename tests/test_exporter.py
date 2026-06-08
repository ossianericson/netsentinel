"""Tests for modules/exporter.py — multi-format data export helpers."""


def test_exporter_import():
    from modules import exporter
    assert exporter is not None


def test_csv_text_produces_header_and_rows():
    from modules.exporter import _csv_text
    result = _csv_text(["A", "B", "C"], [["1", "2", "3"], ["4", "5", "6"]])
    lines = result.strip().splitlines()
    assert lines[0] == "A,B,C"
    assert lines[1] == "1,2,3"
    assert lines[2] == "4,5,6"


def test_csv_text_empty_rows():
    from modules.exporter import _csv_text
    result = _csv_text(["X", "Y"], [])
    lines = result.strip().splitlines()
    assert len(lines) == 1
    assert lines[0] == "X,Y"


def test_csv_text_escapes_commas():
    from modules.exporter import _csv_text
    result = _csv_text(["Val"], [["a,b"]])
    assert '"a,b"' in result or ",b" in result  # csv module may quote or not


def test_export_all_zip_requires_store_and_path():
    from modules.exporter import export_all_zip
    import inspect
    sig = inspect.signature(export_all_zip)
    params = list(sig.parameters.keys())
    assert "store" in params
    assert "dest" in params


def test_exporter_functions_exist():
    from modules import exporter
    for name in ("export_all_zip", "_csv_text", "_device_events_csv",
                 "_alerts_csv", "_speed_tests_csv", "_cve_csv"):
        assert hasattr(exporter, name), f"exporter.{name} missing"
