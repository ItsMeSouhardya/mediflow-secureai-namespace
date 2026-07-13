"""Generate simple, patient-anonymous PDFs for My Health attachment demos."""

from __future__ import annotations

import shutil
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "pdf"
PUBLIC_DIR = ROOT / "public" / "demo-records"

NAVY = colors.HexColor("#0F1E3D")
BLUE = colors.HexColor("#2563EB")
LIGHT_BLUE = colors.HexColor("#EAF3FF")
LINE_BLUE = colors.HexColor("#BCD5F5")
SLATE = colors.HexColor("#475569")

RECORDS = [
    {
        "filename": "DEMO ENCOUNTER.pdf",
        "title": "DEMO ENCOUNTER",
        "record_id": "ENC-260713-104",
        "meta": [("VISIT DATE", "13 Jul 2026"), ("FACILITY", "City Hospital"), ("DEPARTMENT", "General Medicine"), ("STATUS", "Completed")],
        "section": "VISIT SUMMARY",
        "rows": [
            ("Chief concern", "Routine consultation and general fatigue"),
            ("Clinical assessment", "Vitals stable; no urgent warning signs recorded"),
            ("Care plan", "Hydration, regular meals, and follow-up if symptoms persist"),
            ("Follow-up", "Review after 7 days if required"),
        ],
    },
    {
        "filename": "DEMO ALLERGY.pdf",
        "title": "DEMO ALLERGY",
        "record_id": "ALG-260713-218",
        "meta": [("RECORDED ON", "13 Jul 2026"), ("RECORD TYPE", "Allergy declaration"), ("SOURCE", "Patient reported"), ("STATUS", "Active")],
        "section": "ALLERGY DETAILS",
        "rows": [
            ("Substance", "Penicillin"),
            ("Reaction", "Skin rash"),
            ("Severity", "Moderate"),
            ("Clinical note", "Confirm allergy status before prescribing antibiotics"),
        ],
    },
    {
        "filename": "DEMO PRESCRIPTION.pdf",
        "title": "DEMO PRESCRIPTION",
        "record_id": "RX-260713-356",
        "meta": [("ISSUED ON", "13 Jul 2026"), ("FACILITY", "City Hospital"), ("DEPARTMENT", "General Medicine"), ("STATUS", "Active")],
        "section": "PRESCRIPTION DETAILS",
        "rows": [
            ("Medicine", "Paracetamol 500 mg tablet"),
            ("Dosage", "One tablet after food"),
            ("Frequency", "Up to three times daily when required"),
            ("Duration", "3 days"),
            ("Instructions", "Do not exceed the stated daily dose"),
        ],
    },
    {
        "filename": "DEMO VACCINATION.pdf",
        "title": "DEMO VACCINATION",
        "record_id": "VAC-260713-482",
        "meta": [("ADMINISTERED ON", "13 Jul 2026"), ("FACILITY", "City Hospital"), ("RECORD TYPE", "Vaccination certificate"), ("STATUS", "Verified")],
        "section": "VACCINATION DETAILS",
        "rows": [
            ("Vaccine", "Tetanus-Diphtheria booster"),
            ("Dose", "Booster dose"),
            ("Batch number", "TD26-X184"),
            ("Route", "Intramuscular"),
            ("Next action", "Follow routine immunization guidance"),
        ],
    },
]


def build_pdf(record: dict, destination: Path) -> None:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "RecordTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=27,
        textColor=NAVY,
        spaceAfter=5 * mm,
    )
    brand_style = ParagraphStyle(
        "Brand",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=BLUE,
        spaceAfter=10 * mm,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=BLUE,
        spaceBefore=7 * mm,
        spaceAfter=4 * mm,
    )
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=8,
        leading=11,
        textColor=SLATE,
    )

    doc = SimpleDocTemplate(
        str(destination),
        pagesize=A4,
        rightMargin=22 * mm,
        leftMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=record["title"],
        author="MediFlow SecureAI",
    )
    story = [
        Paragraph(record["title"], title_style),
        Paragraph("XYZ CLINICAL RECORDS", brand_style),
    ]

    meta = [["RECORD ID", record["record_id"]]]
    meta.extend([[label, value] for label, value in record["meta"]])
    meta_table = Table(meta, colWidths=[48 * mm, 99 * mm], hAlign="CENTER")
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE),
        ("BACKGROUND", (1, 0), (1, -1), colors.white),
        ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
        ("TEXTCOLOR", (1, 0), (1, -1), SLATE),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE_BLUE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.extend([meta_table, Paragraph(record["section"], section_style)])

    detail_rows = [["FIELD", "DETAIL"]] + [list(row) for row in record["rows"]]
    detail_table = Table(detail_rows, colWidths=[48 * mm, 99 * mm], hAlign="CENTER")
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D7E8FF")),
        ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 1), (0, -1), NAVY),
        ("TEXTCOLOR", (1, 1), (1, -1), SLATE),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FBFF")),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE_BLUE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.extend([
        detail_table,
        Spacer(1, 18 * mm),
        Paragraph(
            "This document contains no patient-identifying information and is provided as a basic upload demonstration file.",
            footer_style,
        ),
    ])
    doc.build(story)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    for record in RECORDS:
        output_path = OUTPUT_DIR / record["filename"]
        build_pdf(record, output_path)
        shutil.copy2(output_path, PUBLIC_DIR / record["filename"])
        print(output_path)


if __name__ == "__main__":
    main()
