"""Build every output of a query into one folder: charts, workbook, summary and Word report."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .analysis import Analysis
from .charts import Charts, setup_style
from .cpi import load_cpi
from .model import Query, QueryData
from .summary import write_summary
from .word import write_report
from .workbook import write_workbook

CPI_FILE = Path(__file__).resolve().parent.parent / "data" / "meta" / "us_cpi_worldbank.csv"


@dataclass
class Outputs:
    folder: Path
    workbook: Path
    summary: Path
    report: Path
    charts: list[Path] = field(default_factory=list)
    extra: dict[str, str] = field(default_factory=dict)


def _fresh_folder(path: Path) -> Path:
    """A chart folder emptied of earlier PNGs, so a re-run leaves no stale charts behind."""
    path.mkdir(parents=True, exist_ok=True)
    for old in path.glob("*.png"):
        old.unlink()
    return path


def build_report(query: Query, data: QueryData, out_root: Path) -> tuple[Outputs, Analysis]:
    folder = out_root / query.folder_name
    folder.mkdir(parents=True, exist_ok=True)
    cpi, cpi_note = load_cpi(CPI_FILE)
    analysis = Analysis.of(query, data, cpi, cpi_note)

    setup_style()
    charts = Charts(analysis, _fresh_folder(folder / "charts")).make_all()

    workbook = folder / f"{query.folder_name}.xlsx"
    files = {"Workbook": workbook.name, "Report": "report.docx", "Summary": "summary.md",
             "Charts": f"charts/ ({len(charts)} PNG files)"}
    try:
        write_workbook(workbook, analysis, data, charts, files)
        summary = write_summary(analysis, folder / "summary.md", files)
        report = write_report(analysis, charts, folder / "report.docx", files)
    except PermissionError as err:
        raise PermissionError(f"Cannot write {err.filename}: it is probably open in Excel or "
                              "Word. Close it and run the query again.") from err
    extra = {k: v for k, v in files.items() if k in ("Raw data", "Data gaps", "Source estimates")}
    return Outputs(folder, workbook, summary, report, charts, extra), analysis
