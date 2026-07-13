"""Ensure the downloadable prototype reports produce their promised outputs."""

from pathlib import Path

import pypdf

from report_analysis import analyse_report_text


ROOT = Path(__file__).resolve().parents[2]


def extract(filename: str):
    path = ROOT / "output" / "pdf" / filename
    reader = pypdf.PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Patient Name" not in text
    return analyse_report_text(text, extraction_confidence=1.0)


def test_demo_report_2_produces_expected_risk_pattern():
    result = extract("DEMO REPORT 2.pdf")
    assert len(result.extracted_biomarkers) == 16
    assert set(result.abnormal_flags) == {
        "Fasting Blood Glucose", "HbA1c", "Total Cholesterol",
        "LDL Cholesterol", "HDL Cholesterol", "Triglycerides",
        "SGPT (ALT)", "SGOT (AST)", "BMI",
    }
    assert "may be indicative of diabetes mellitus" in result.summary
    assert "dyslipidaemia" in result.summary
    assert result.confidence_score == 1.0


def test_demo_report_1_produces_all_normal_output():
    result = extract("DEMO REPORT 1.pdf")
    assert len(result.extracted_biomarkers) == 16
    assert result.abnormal_flags == []
    assert "No diseases detected" in result.summary
    assert result.confidence_score == 1.0
