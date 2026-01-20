import tempfile
from pathlib import Path

from gps_agents.export.gedcom import export_gedcom


def test_export_gedcom_minimal(tmp_path: Path) -> None:
    out = tmp_path / "out.ged"
    # With an empty ledger, exporter should still create a valid GEDCOM skeleton
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)

    result = export_gedcom(ledger_dir=ledger_dir, out_file=out)
    assert result.exists()
    head = result.read_text().splitlines()[0].strip()
    assert head.startswith("0 HEAD")
