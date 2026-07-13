"""Generate anonymous, text-extractable PDF reports for prototype demonstrations."""

from pathlib import Path
from shutil import copy2

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf"
PUBLIC = ROOT / "public" / "demo-reports"

NAVY = colors.HexColor("#0F1E3D")
BLUE = colors.HexColor("#2563EB")
LIGHT_BLUE = colors.HexColor("#DBEAFE")
PALE_BLUE = colors.HexColor("#EFF6FF")
SLATE = colors.HexColor("#475569")
GREEN = colors.HexColor("#15803D")
AMBER = colors.HexColor("#B45309")
RED = colors.HexColor("#B91C1C")


def status_color(status: str):
    return {"NORMAL": GREEN, "HIGH": RED, "LOW": AMBER}.get(status, SLATE)


def build_report(filename: str, report_title: str, report_id: str, panels: list[tuple], interpretation: list[str]):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / filename
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=report_title, author="MediFlow AI Prototype Laboratory",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=NAVY, alignment=TA_LEFT, spaceAfter=5)
    eyebrow = ParagraphStyle("Eyebrow", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=BLUE, tracking=1.5)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.5, leading=14, textColor=SLATE)
    small = ParagraphStyle("Small", parent=body, fontSize=8, leading=11)
    section = ParagraphStyle("Section", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=NAVY, spaceBefore=8, spaceAfter=6)

    story = [
        Table([[Paragraph("MEDIFLOW DIAGNOSTICS", eyebrow), Paragraph("PROTOTYPE LAB REPORT", ParagraphStyle("right", parent=eyebrow, alignment=2))]], colWidths=[85 * mm, 73 * mm], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("BOX", (0, 0), (-1, -1), 0, NAVY), ("TEXTCOLOR", (0, 0), (-1, -1), colors.white), ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)])),
        Spacer(1, 9 * mm),
        Paragraph(report_title, title),
        Paragraph("Anonymous demonstration specimen - no patient identity included", body),
        Spacer(1, 5 * mm),
        Table([
            [Paragraph("REPORT ID", eyebrow), Paragraph("COLLECTED", eyebrow), Paragraph("SPECIMEN", eyebrow)],
            [Paragraph(report_id, body), Paragraph("12 July 2026, 08:30", body), Paragraph("Demo serum / whole blood", body)],
        ], colWidths=[52 * mm, 52 * mm, 54 * mm], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE), ("GRID", (0, 0), (-1, -1), 0.5, LIGHT_BLUE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)])),
        Spacer(1, 6 * mm),
        Paragraph("Laboratory results", section),
    ]

    rows = [["PARAMETER", "RESULT", "UNIT", "REFERENCE RANGE", "STATUS"]]
    for name, value, unit, reference, status in panels:
        rows.append([name, str(value), unit, reference, status])
    table = Table(rows, colWidths=[52 * mm, 23 * mm, 25 * mm, 36 * mm, 22 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BLUE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"), ("TEXTCOLOR", (0, 1), (0, -1), NAVY),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5), ("GRID", (0, 0), (-1, -1), 0.5, LIGHT_BLUE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_BLUE]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]
    for index, row in enumerate(panels, start=1):
        style.extend([("TEXTCOLOR", (4, index), (4, index), status_color(row[4])), ("FONTNAME", (4, index), (4, index), "Helvetica-Bold")])
    table.setStyle(TableStyle(style))
    story.extend([table, Spacer(1, 6 * mm), Paragraph("Prototype interpretation", section)])
    for item in interpretation:
        story.append(Paragraph(f"- {item}", body))
        story.append(Spacer(1, 1.5 * mm))
    story.extend([
        Spacer(1, 5 * mm),
        Table([[Paragraph("DECISION SUPPORT NOTICE", eyebrow)], [Paragraph("This anonymous report is synthetic and intended only for demonstrating MediFlow's extraction and flagging workflow. It is not a diagnosis, prescription, or clinical opinion. All automated findings require review by a qualified clinician.", small)]], colWidths=[158 * mm], style=TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE), ("BACKGROUND", (0, 1), (-1, 1), PALE_BLUE), ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#93C5FD")), ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)])),
        Spacer(1, 4 * mm),
        Paragraph("Generated for MediFlow AI prototype demonstration | Upload document type: Lab report", ParagraphStyle("footer", parent=small, alignment=TA_CENTER, textColor=SLATE)),
    ])
    doc.build(story)
    copy2(path, PUBLIC / filename)


def main():
    build_report(
        "demo_metabolic_risk_report.pdf", "Comprehensive Metabolic and Lipid Panel", "DEMO-MET-260712",
        [
            ("Fasting Blood Glucose", "148", "mg/dL", "70 - 100", "HIGH"),
            ("HbA1c", "7.4", "%", "4.0 - 5.7", "HIGH"),
            ("Total Cholesterol", "224", "mg/dL", "Below 200", "HIGH"),
            ("LDL Cholesterol", "142", "mg/dL", "Below 100", "HIGH"),
            ("HDL Cholesterol", "36", "mg/dL", "40 or higher", "LOW"),
            ("Triglycerides", "210", "mg/dL", "Below 150", "HIGH"),
            ("Creatinine", "0.9", "mg/dL", "0.6 - 1.2", "NORMAL"),
            ("ALT", "34", "U/L", "Below 40", "NORMAL"),
            ("BMI", "31.2", "kg/m2", "18.5 - 24.9", "HIGH"),
        ],
        ["Glucose and HbA1c are above the provided reference ranges.", "The lipid pattern includes elevated LDL and triglycerides with low HDL.", "Creatinine and ALT are within the provided reference ranges."],
    )
    build_report(
        "demo_wellness_report.pdf", "Routine Wellness Laboratory Panel", "DEMO-WELL-260712",
        [
            ("Haemoglobin", "14.2", "g/dL", "12.0 - 17.5", "NORMAL"),
            ("Fasting Blood Glucose", "88", "mg/dL", "70 - 100", "NORMAL"),
            ("HbA1c", "5.3", "%", "4.0 - 5.7", "NORMAL"),
            ("Creatinine", "0.8", "mg/dL", "0.6 - 1.2", "NORMAL"),
            ("TSH", "2.1", "mIU/L", "0.4 - 4.0", "NORMAL"),
            ("Serum Sodium", "140", "mEq/L", "136 - 145", "NORMAL"),
            ("Serum Potassium", "4.3", "mEq/L", "3.5 - 5.1", "NORMAL"),
            ("ALT", "24", "U/L", "Below 40", "NORMAL"),
        ],
        ["All listed biomarkers are within the provided reference ranges.", "The report demonstrates a high-confidence normal extraction scenario.", "Routine clinical interpretation must still consider history, symptoms, and clinician review."],
    )


if __name__ == "__main__":
    main()
