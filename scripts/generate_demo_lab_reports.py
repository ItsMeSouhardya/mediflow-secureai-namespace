from __future__ import annotations

from pathlib import Path
from shutil import copyfile

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "pdf"
PUBLIC_DIR = ROOT / "public" / "demo-reports"

REFERENCE_RANGES = {
    "Fasting Blood Glucose": "70 - 100 mg/dL",
    "HbA1c": "4.0 - 5.7 %",
    "Total Cholesterol": "Up to 200 mg/dL",
    "LDL Cholesterol": "Up to 100 mg/dL",
    "HDL Cholesterol": "40 mg/dL or higher",
    "Triglycerides": "Up to 150 mg/dL",
    "Creatinine": "0.6 - 1.2 mg/dL",
    "Haemoglobin": "12.0 - 17.5 g/dL",
    "WBC": "4.0 - 11.0 10^9/L",
    "Platelet Count": "150 - 400 10^9/L",
    "TSH": "0.4 - 4.0 mIU/L",
    "Serum Sodium": "136 - 145 mmol/L",
    "Serum Potassium": "3.5 - 5.1 mmol/L",
    "SGPT": "Up to 40 U/L",
    "SGOT": "Up to 40 U/L",
    "BMI": "18.5 - 24.9 kg/m2",
}

REPORTS = [
    {
        "label": "DEMO REPORT 1",
        "filename": "DEMO REPORT 1.pdf",
        "report_id": "XYZ-260713-N184",
        "collected_at": "13 Jul 2026, 07:45 AM",
        "sample": "Venous blood - fasting",
        "results": [
            ("Fasting Blood Glucose", "89", "mg/dL", "Normal"),
            ("HbA1c", "5.3", "%", "Normal"),
            ("Total Cholesterol", "172", "mg/dL", "Normal"),
            ("LDL Cholesterol", "88", "mg/dL", "Normal"),
            ("HDL Cholesterol", "54", "mg/dL", "Normal"),
            ("Triglycerides", "112", "mg/dL", "Normal"),
            ("Creatinine", "0.9", "mg/dL", "Normal"),
            ("Haemoglobin", "14.2", "g/dL", "Normal"),
            ("WBC", "7.1", "10^9/L", "Normal"),
            ("Platelet Count", "265", "10^9/L", "Normal"),
            ("TSH", "2.1", "mIU/L", "Normal"),
            ("Serum Sodium", "140", "mmol/L", "Normal"),
            ("Serum Potassium", "4.3", "mmol/L", "Normal"),
            ("SGPT", "24", "U/L", "Normal"),
            ("SGOT", "22", "U/L", "Normal"),
            ("BMI", "22.4", "kg/m2", "Normal"),
        ],
    },
    {
        "label": "DEMO REPORT 2",
        "filename": "DEMO REPORT 2.pdf",
        "report_id": "XYZ-260713-R627",
        "collected_at": "13 Jul 2026, 08:20 AM",
        "sample": "Venous blood - fasting",
        "results": [
            ("Fasting Blood Glucose", "168", "mg/dL", "High"),
            ("HbA1c", "8.2", "%", "High"),
            ("Total Cholesterol", "245", "mg/dL", "High"),
            ("LDL Cholesterol", "160", "mg/dL", "High"),
            ("HDL Cholesterol", "32", "mg/dL", "Low"),
            ("Triglycerides", "260", "mg/dL", "High"),
            ("Creatinine", "1.0", "mg/dL", "Normal"),
            ("Haemoglobin", "13.9", "g/dL", "Normal"),
            ("WBC", "8.4", "10^9/L", "Normal"),
            ("Platelet Count", "285", "10^9/L", "Normal"),
            ("TSH", "2.3", "mIU/L", "Normal"),
            ("Serum Sodium", "139", "mmol/L", "Normal"),
            ("Serum Potassium", "4.5", "mmol/L", "Normal"),
            ("SGPT", "52", "U/L", "High"),
            ("SGOT", "44", "U/L", "High"),
            ("BMI", "32.8", "kg/m2", "High"),
        ],
    },
]


def _status_cell(value: str, style: ParagraphStyle) -> Paragraph:
    color = "#047857" if value == "Normal" else "#b45309" if value in {"High", "Low"} else "#334155"
    return Paragraph(f'<font color="{color}"><b>{value}</b></font>', style)


def build_report(report: dict[str, object], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DiagnosticTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=22, leading=26, textColor=colors.HexColor("#0f1e3d"), alignment=TA_CENTER,
        spaceAfter=3 * mm,
    )
    label_style = ParagraphStyle(
        "ReportLabel", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=9, leading=12, textColor=colors.HexColor("#2563eb"), alignment=TA_CENTER,
        spaceAfter=6 * mm,
    )
    body_style = ParagraphStyle(
        "ReportBody", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8.2, leading=10, textColor=colors.HexColor("#334155"),
    )
    body_bold = ParagraphStyle(
        "ReportBodyBold", parent=body_style, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0f1e3d"),
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=10, leading=13, textColor=colors.HexColor("#1d4ed8"),
        spaceBefore=4 * mm, spaceAfter=3 * mm,
    )
    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"], fontName="Helvetica",
        fontSize=7.2, leading=9, textColor=colors.HexColor("#64748b"), alignment=TA_CENTER,
    )

    document = SimpleDocTemplate(
        str(destination), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm,
        topMargin=14 * mm, bottomMargin=13 * mm,
        title=str(report["label"]), author="XYZ DIAGNOSTICS",
    )
    story = [
        Paragraph("XYZ DIAGNOSTICS", title_style),
        Paragraph(str(report["label"]), label_style),
    ]

    metadata = Table([
        [Paragraph("REPORT ID", body_bold), Paragraph(str(report["report_id"]), body_style),
         Paragraph("COLLECTED AT", body_bold), Paragraph(str(report["collected_at"]), body_style)],
        [Paragraph("SAMPLE COLLECTED", body_bold), Paragraph(str(report["sample"]), body_style),
         Paragraph("REPORT STATUS", body_bold), Paragraph("Final", body_style)],
    ], colWidths=[31 * mm, 52 * mm, 34 * mm, 49 * mm], rowHeights=[11 * mm, 11 * mm])
    metadata.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#bfdbfe")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbeafe")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([metadata, Paragraph("LABORATORY RESULTS", section_style)])

    rows = [[
        Paragraph("PARAMETER", body_bold), Paragraph("RESULT", body_bold),
        Paragraph("UNIT", body_bold), Paragraph("REFERENCE RANGE", body_bold),
        Paragraph("STATUS", body_bold),
    ]]
    for parameter, result, unit, status in report["results"]:
        rows.append([
            Paragraph(parameter, body_bold), Paragraph(result, body_style), Paragraph(unit, body_style),
            Paragraph(REFERENCE_RANGES[parameter], body_style), _status_cell(status, body_style),
        ])

    table = Table(rows, colWidths=[48 * mm, 21 * mm, 23 * mm, 52 * mm, 22 * mm], repeatRows=1)
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#bfdbfe")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbeafe")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for row_index in range(1, len(rows)):
        if row_index % 2 == 0:
            table_style.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#f8fbff")))
    table.setStyle(TableStyle(table_style))
    story.extend([
        KeepTogether(table), Spacer(1, 5 * mm),
        Paragraph("This report contains no patient-identifying information and is prepared solely for prototype demonstration.", footer_style),
    ])
    document.build(story)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    for report in REPORTS:
        output_path = OUTPUT_DIR / str(report["filename"])
        build_report(report, output_path)
        copyfile(output_path, PUBLIC_DIR / str(report["filename"]))
        print(output_path)


if __name__ == "__main__":
    main()
