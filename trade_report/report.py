"""Build every output of a query into one folder: charts, workbook, summary and Word report. A
query with a partner gets the partner report, on the trade between the two countries."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .analysis import Analysis
from .charts import Charts, setup_style
from .cpi import load_cpi
from .model import Query, QueryData
from .partner import charts as partner_charts, summary as partner_summary
from .partner import word as partner_word, workbook as partner_workbook
from .partner.analysis import PartnerAnalysis
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


def build_report(query: Query, data: QueryData,
                 out_root: Path) -> tuple[Outputs, Analysis | PartnerAnalysis]:
    folder = out_root / query.folder_name
    folder.mkdir(parents=True, exist_ok=True)
    cpi, cpi_note = load_cpi(CPI_FILE)
    partner = query.partner_code is not None
    if partner:
        analysis = PartnerAnalysis(query, data, cpi, cpi_note)
        make_charts, writers = partner_charts.PartnerCharts, (
            partner_workbook.write_workbook, partner_summary.write_summary,
            partner_word.write_report)
    else:
        analysis = Analysis.of(query, data, cpi, cpi_note)
        make_charts, writers = Charts, (write_workbook, write_summary, write_report)

    setup_style()
    charts = make_charts(analysis, _fresh_folder(folder / "charts")).make_all()

    workbook = folder / f"{query.folder_name}.xlsx"
    files = {"Workbook": workbook.name, "Report": "report.docx", "Summary": "summary.md",
             "Charts": f"charts/ ({len(charts)} PNG files)"}
    workbook_writer, summary_writer, report_writer = writers
    try:
        workbook_writer(workbook, analysis, data, charts, files)
        summary = summary_writer(analysis, folder / "summary.md", files)
        report = report_writer(analysis, charts, folder / "report.docx", files)
    except PermissionError as err:
        raise PermissionError(f"Cannot write {err.filename}: it is probably open in Excel or "
                              "Word. Close it and run the query again.") from err
    extra = {k: v for k, v in files.items()
             if k in ("Data gaps", "Source estimates") or k.startswith("Raw data")}
    return Outputs(folder, workbook, summary, report, charts, extra), analysis
