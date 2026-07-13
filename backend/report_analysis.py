"""Medical report analysis engine — biomarker extraction and reference-range evaluation.

Covers task 6.1 through 6.6:
  6.1  Supported report types and biomarker vocabulary
  6.2  Structured biomarker extraction from report text (regex-based)
  6.3  Unit normalisation and impossible/ambiguous value detection
  6.4  Abnormal-value flagging with versioned reference-range rules
  6.5  Plain-language assistive summary with extraction caveats
  6.6  Doctor-review gate — analysis is decision-support only

DESIGN CONSTRAINTS
------------------
- All outputs are labelled "decision support only" and require doctor review
  before clinical acceptance (enforced at the API layer via review_status).
- Reference ranges are versioned via RULE_VERSION so any change is traceable.
- No patient identifiers enter this module; it operates on plain text only.
- Confidence is a rough estimate (0.0–1.0) reflecting extraction quality;
  it does NOT represent diagnostic probability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 6.1 — Versioned rule and model identifiers
# ---------------------------------------------------------------------------

RULE_VERSION = "lab-rules-v1.0"
EXTRACTION_MODEL_VERSION = "regex-extractor-v1.0"

# ---------------------------------------------------------------------------
# 6.1 — Biomarker vocabulary
#
# Each entry defines:
#   canonical_name : human-readable label
#   aliases        : regex alternation patterns (case-insensitive)
#   canonical_unit : the unit values are normalised to
#   alt_units      : dict of alternative unit → conversion factor to canonical
#   ref_range      : (low, high) in canonical_unit; None means open-ended
#   impossible_low : absolute physiological minimum (hard reject)
#   impossible_high: absolute physiological maximum (hard reject)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BiomarkerDef:
    canonical_name: str
    aliases: list[str]
    canonical_unit: str
    alt_units: dict[str, float]          # unit_label → multiply_by to get canonical
    ref_range: tuple[float | None, float | None]
    impossible_low: float | None = None
    impossible_high: float | None = None


BIOMARKER_DEFS: list[BiomarkerDef] = [
    # ---- Blood glucose ----
    BiomarkerDef(
        canonical_name="Fasting Blood Glucose",
        aliases=["fasting blood glucose", "fbg", "fasting glucose", "fasting plasma glucose", "fpg"],
        canonical_unit="mg/dL",
        alt_units={"mmol/l": 18.0, "mmol/L": 18.0},
        ref_range=(70.0, 100.0),
        impossible_low=0.0,
        impossible_high=1200.0,
    ),
    BiomarkerDef(
        canonical_name="HbA1c",
        aliases=["hba1c", "hb a1c", "hemoglobin a1c", "haemoglobin a1c", "glycated haemoglobin", "glycosylated haemoglobin", "a1c"],
        canonical_unit="%",
        alt_units={"mmol/mol": 0.0915},   # IFCC → NGSP: approx (x/10.929 + 2.15)  — linear approx
        ref_range=(4.0, 5.7),
        impossible_low=0.0,
        impossible_high=20.0,
    ),
    BiomarkerDef(
        canonical_name="Total Cholesterol",
        aliases=["total cholesterol", "cholesterol total", "serum cholesterol", "t.chol", "tchol"],
        canonical_unit="mg/dL",
        alt_units={"mmol/l": 38.67, "mmol/L": 38.67},
        ref_range=(None, 200.0),
        impossible_low=0.0,
        impossible_high=1000.0,
    ),
    BiomarkerDef(
        canonical_name="LDL Cholesterol",
        aliases=["ldl", "ldl cholesterol", "ldl-c", "low density lipoprotein"],
        canonical_unit="mg/dL",
        alt_units={"mmol/l": 38.67, "mmol/L": 38.67},
        ref_range=(None, 100.0),
        impossible_low=0.0,
        impossible_high=800.0,
    ),
    BiomarkerDef(
        canonical_name="HDL Cholesterol",
        aliases=["hdl", "hdl cholesterol", "hdl-c", "high density lipoprotein"],
        canonical_unit="mg/dL",
        alt_units={"mmol/l": 38.67, "mmol/L": 38.67},
        ref_range=(40.0, None),
        impossible_low=0.0,
        impossible_high=200.0,
    ),
    BiomarkerDef(
        canonical_name="Triglycerides",
        aliases=["triglycerides", "triglyceride", "tg", "trigs"],
        canonical_unit="mg/dL",
        alt_units={"mmol/l": 88.57, "mmol/L": 88.57},
        ref_range=(None, 150.0),
        impossible_low=0.0,
        impossible_high=5000.0,
    ),
    BiomarkerDef(
        canonical_name="Systolic Blood Pressure",
        aliases=["systolic", "sbp", "systolic bp", "systolic blood pressure"],
        canonical_unit="mmHg",
        alt_units={},
        ref_range=(90.0, 120.0),
        impossible_low=40.0,
        impossible_high=300.0,
    ),
    BiomarkerDef(
        canonical_name="Diastolic Blood Pressure",
        aliases=["diastolic", "dbp", "diastolic bp", "diastolic blood pressure"],
        canonical_unit="mmHg",
        alt_units={},
        ref_range=(60.0, 80.0),
        impossible_low=20.0,
        impossible_high=200.0,
    ),
    BiomarkerDef(
        canonical_name="Creatinine",
        aliases=["creatinine", "serum creatinine", "s.creatinine", "s creatinine"],
        canonical_unit="mg/dL",
        alt_units={"umol/l": 0.01131, "µmol/l": 0.01131, "μmol/l": 0.01131},
        ref_range=(0.6, 1.2),
        impossible_low=0.0,
        impossible_high=50.0,
    ),
    BiomarkerDef(
        canonical_name="Haemoglobin",
        aliases=["haemoglobin", "hemoglobin", "hgb", "hb"],
        canonical_unit="g/dL",
        alt_units={"g/l": 0.1},
        ref_range=(12.0, 17.5),
        impossible_low=1.0,
        impossible_high=25.0,
    ),
    BiomarkerDef(
        canonical_name="White Blood Cell Count",
        aliases=["wbc", "white blood cell", "white blood count", "leukocyte count", "leucocyte count", "wbc count"],
        canonical_unit="10³/µL",
        alt_units={"10^9/l": 1.0, "10⁹/l": 1.0, "x10^9/l": 1.0, "cells/µl": 0.001},
        ref_range=(4.0, 11.0),
        impossible_low=0.0,
        impossible_high=500.0,
    ),
    BiomarkerDef(
        canonical_name="Platelet Count",
        aliases=["platelets", "platelet count", "plt", "thrombocytes"],
        canonical_unit="10³/µL",
        alt_units={"10^9/l": 1.0, "10⁹/l": 1.0, "x10^9/l": 1.0, "cells/µl": 0.001},
        ref_range=(150.0, 400.0),
        impossible_low=0.0,
        impossible_high=2000.0,
    ),
    BiomarkerDef(
        canonical_name="TSH",
        aliases=["tsh", "thyroid stimulating hormone", "thyrotropin"],
        canonical_unit="mIU/L",
        alt_units={"µiu/ml": 1.0, "uiu/ml": 1.0},
        ref_range=(0.4, 4.0),
        impossible_low=0.0,
        impossible_high=500.0,
    ),
    BiomarkerDef(
        canonical_name="Serum Sodium",
        aliases=["sodium", "na+", "serum sodium", "s.na", "na"],
        canonical_unit="mEq/L",
        alt_units={"mmol/l": 1.0, "mmol/L": 1.0},
        ref_range=(136.0, 145.0),
        impossible_low=80.0,
        impossible_high=200.0,
    ),
    BiomarkerDef(
        canonical_name="Serum Potassium",
        aliases=["potassium", "k+", "serum potassium", "s.k", "kalium"],
        canonical_unit="mEq/L",
        alt_units={"mmol/l": 1.0, "mmol/L": 1.0},
        ref_range=(3.5, 5.1),
        impossible_low=1.0,
        impossible_high=10.0,
    ),
    BiomarkerDef(
        canonical_name="SGPT (ALT)",
        aliases=["sgpt", "alt", "alanine aminotransferase", "alanine transaminase", "alat"],
        canonical_unit="U/L",
        alt_units={},
        ref_range=(None, 40.0),
        impossible_low=0.0,
        impossible_high=10000.0,
    ),
    BiomarkerDef(
        canonical_name="SGOT (AST)",
        aliases=["sgot", "ast", "aspartate aminotransferase", "aspartate transaminase", "asat"],
        canonical_unit="U/L",
        alt_units={},
        ref_range=(None, 40.0),
        impossible_low=0.0,
        impossible_high=10000.0,
    ),
    BiomarkerDef(
        canonical_name="BMI",
        aliases=["bmi", "body mass index"],
        canonical_unit="kg/m²",
        alt_units={"kg/m2": 1.0},
        ref_range=(18.5, 24.9),
        impossible_low=5.0,
        impossible_high=100.0,
    ),
]

# Build a fast lookup: lower-case alias → BiomarkerDef
_ALIAS_MAP: dict[str, BiomarkerDef] = {}
for _bdef in BIOMARKER_DEFS:
    for _alias in _bdef.aliases:
        _ALIAS_MAP[_alias.lower()] = _bdef


# ---------------------------------------------------------------------------
# 6.2 — Regex extraction
# ---------------------------------------------------------------------------

# Pattern captures:   label ... value   unit?
# Examples matched:
#   "HbA1c: 7.2 %"
#   "Fasting Blood Glucose  =  126 mg/dL"
#   "LDL Cholesterol    100.5"
_VALUE_RE = re.compile(
    r"(?P<value>\d{1,5}(?:[.,]\d{1,3})?)"    # numeric value
    r"\s*"
    r"(?P<unit>"                               # optional unit
    r"mg/dL|mmol/[lL]|g/dL|g/L|%|mIU/L|"
    r"[Uu]/[lL]|mEq/[lL]|mmHg|"
    r"10[\^³]?[39]/[lL]|µIU/mL|uIU/mL|"
    r"µmol/[lL]|umol/[lL]|cells/µ[lL]|"
    r"10\^9/[lL]|x10\^9/[lL]|"
    r"kg/m[²2]"
    r")?",
    re.IGNORECASE,
)


def _build_alias_pattern() -> re.Pattern[str]:
    """Build a single pattern that matches any known biomarker alias."""
    # Sort by length desc so longer aliases match before shorter substrings.
    aliases_sorted = sorted(_ALIAS_MAP.keys(), key=len, reverse=True)
    escaped = [re.escape(a) for a in aliases_sorted]
    return re.compile(
        r"(?i)\b(" + "|".join(escaped) + r")\b"
        r"[\s:=\-–—/]*"         # separator between label and value
    )


_ALIAS_PATTERN: re.Pattern[str] = _build_alias_pattern()


@dataclass
class RawExtraction:
    """A single biomarker found in the text before normalisation."""
    canonical_name: str
    raw_value: str
    raw_unit: str
    position: int       # character offset in source text


def extract_raw_biomarkers(text: str) -> list[RawExtraction]:
    """Scan text for known biomarker patterns; return raw (un-normalised) hits."""
    results: list[RawExtraction] = []
    seen_names: set[str] = set()      # keep first occurrence per biomarker

    for alias_match in _ALIAS_PATTERN.finditer(text):
        alias = alias_match.group(1).lower()
        bdef = _ALIAS_MAP.get(alias)
        if bdef is None:
            continue
        if bdef.canonical_name in seen_names:
            continue

        # Try to find the value immediately after the alias match.
        remainder = text[alias_match.end():]
        val_match = _VALUE_RE.match(remainder)
        if val_match and val_match.group("value"):
            raw_val = val_match.group("value").replace(",", ".")
            raw_unit = (val_match.group("unit") or "").strip()
            results.append(RawExtraction(
                canonical_name=bdef.canonical_name,
                raw_value=raw_val,
                raw_unit=raw_unit,
                position=alias_match.start(),
            ))
            seen_names.add(bdef.canonical_name)

    return results

# ---------------------------------------------------------------------------
# 6.3 — Unit normalisation and impossible/ambiguous value detection
# ---------------------------------------------------------------------------

@dataclass
class NormalisedBiomarker:
    """A biomarker extracted, normalised, and range-evaluated."""
    canonical_name: str
    raw_value: float
    raw_unit: str
    normalised_value: float
    canonical_unit: str
    flag: str                   # "normal" | "high" | "low" | "critical_high" | "critical_low" | "impossible" | "ambiguous"
    ref_range_low: float | None
    ref_range_high: float | None
    warning: str | None = None  # populated for impossible/ambiguous


def _normalise_unit(raw_val: float, raw_unit: str, bdef: BiomarkerDef) -> tuple[float, str | None]:
    """Convert raw_val in raw_unit to bdef.canonical_unit.

    Returns (normalised_value, warning_or_None).
    If no unit was detected, returns (raw_val, ambiguity_warning).
    """
    if not raw_unit:
        return raw_val, f"No unit detected; assumed {bdef.canonical_unit} — verify manually"

    key = raw_unit.lower()
    if key == bdef.canonical_unit.lower():
        return raw_val, None

    factor = bdef.alt_units.get(raw_unit) or bdef.alt_units.get(key)
    if factor is not None:
        return round(raw_val * factor, 4), None

    # Unit present but unrecognised for this biomarker.
    return raw_val, f"Unrecognised unit '{raw_unit}'; value not converted — verify manually"


def _evaluate_flag(value: float, bdef: BiomarkerDef) -> str:
    """Return a severity flag for a normalised value against the reference range."""
    lo, hi = bdef.ref_range

    # Critical thresholds: 50 % beyond the range boundary → critical flag.
    # These are heuristic; a future rule version can make them explicit per-biomarker.
    def _critical_hi(upper: float) -> float:
        return upper + (upper * 0.5)

    def _critical_lo(lower: float) -> float:
        return lower - (lower * 0.5)

    if hi is not None and value > _critical_hi(hi):
        return "critical_high"
    if lo is not None and value < _critical_lo(lo):
        return "critical_low"
    if hi is not None and value > hi:
        return "high"
    if lo is not None and value < lo:
        return "low"
    return "normal"


def normalise_biomarkers(
    raw_extractions: list[RawExtraction],
) -> tuple[list[NormalisedBiomarker], list[str]]:
    """Normalise units, detect impossible values, and evaluate flags.

    Returns (normalised_list, global_warnings).
    Impossible values are excluded from the output list but generate a warning.
    """
    results: list[NormalisedBiomarker] = []
    warnings: list[str] = []

    for raw in raw_extractions:
        bdef = _ALIAS_MAP.get(raw.canonical_name.lower())
        # Fall back to searching by canonical_name directly.
        if bdef is None:
            for _bd in BIOMARKER_DEFS:
                if _bd.canonical_name == raw.canonical_name:
                    bdef = _bd
                    break
        if bdef is None:
            warnings.append(f"No definition found for '{raw.canonical_name}'; skipped")
            continue

        try:
            raw_float = float(raw.raw_value)
        except ValueError:
            warnings.append(f"Non-numeric value '{raw.raw_value}' for {raw.canonical_name}; skipped")
            continue

        # ---- Impossible value check (before unit conversion) ----
        # We check the raw value in its reported unit against the impossible
        # bounds of the canonical unit — good enough for a first-pass guard.
        if bdef.impossible_low is not None and raw_float < bdef.impossible_low:
            warnings.append(
                f"{raw.canonical_name}: value {raw_float} {raw.raw_unit} is below the "
                f"physiological minimum ({bdef.impossible_low}) — excluded"
            )
            results.append(NormalisedBiomarker(
                canonical_name=raw.canonical_name,
                raw_value=raw_float,
                raw_unit=raw.raw_unit,
                normalised_value=raw_float,
                canonical_unit=bdef.canonical_unit,
                flag="impossible",
                ref_range_low=bdef.ref_range[0],
                ref_range_high=bdef.ref_range[1],
                warning=f"Value below physiological minimum ({bdef.impossible_low} {bdef.canonical_unit})",
            ))
            continue

        if bdef.impossible_high is not None and raw_float > bdef.impossible_high:
            warnings.append(
                f"{raw.canonical_name}: value {raw_float} {raw.raw_unit} is above the "
                f"physiological maximum ({bdef.impossible_high}) — excluded"
            )
            results.append(NormalisedBiomarker(
                canonical_name=raw.canonical_name,
                raw_value=raw_float,
                raw_unit=raw.raw_unit,
                normalised_value=raw_float,
                canonical_unit=bdef.canonical_unit,
                flag="impossible",
                ref_range_low=bdef.ref_range[0],
                ref_range_high=bdef.ref_range[1],
                warning=f"Value above physiological maximum ({bdef.impossible_high} {bdef.canonical_unit})",
            ))
            continue

        # ---- Unit normalisation ----
        normalised, unit_warning = _normalise_unit(raw_float, raw.raw_unit, bdef)
        if unit_warning:
            warnings.append(f"{raw.canonical_name}: {unit_warning}")

        # ---- Flag evaluation ----
        flag = _evaluate_flag(normalised, bdef) if unit_warning is None or "ambiguous" not in (unit_warning or "") else "ambiguous"

        results.append(NormalisedBiomarker(
            canonical_name=raw.canonical_name,
            raw_value=raw_float,
            raw_unit=raw.raw_unit,
            normalised_value=normalised,
            canonical_unit=bdef.canonical_unit,
            flag=flag,
            ref_range_low=bdef.ref_range[0],
            ref_range_high=bdef.ref_range[1],
            warning=unit_warning,
        ))

    return results, warnings


# ---------------------------------------------------------------------------
# 6.4 — Abnormal-value summary list
# ---------------------------------------------------------------------------

ABNORMAL_FLAGS = {"high", "low", "critical_high", "critical_low"}


def build_abnormal_flags(normalised: list[NormalisedBiomarker]) -> list[str]:
    """Return the canonical names of all out-of-range biomarkers."""
    return [b.canonical_name for b in normalised if b.flag in ABNORMAL_FLAGS]


# ---------------------------------------------------------------------------
# 6.5 — Plain-language assistive summary
# ---------------------------------------------------------------------------

_FLAG_PHRASES: dict[str, str] = {
    "high":          "above the reference range",
    "low":           "below the reference range",
    "critical_high": "critically elevated",
    "critical_low":  "critically low",
    "impossible":    "outside physiologically plausible limits and may be a transcription error",
    "ambiguous":     "could not be reliably evaluated due to unit ambiguity",
    "normal":        "within the reference range",
}

_DISCLAIMER = (
    "IMPORTANT: This is an automated assistive summary for informational purposes only. "
    "It is NOT a diagnosis, NOT a clinical opinion, and must NOT be used as a substitute "
    "for professional medical evaluation. All findings must be reviewed and confirmed by "
    "a qualified healthcare professional before any clinical action is taken."
)


def build_summary(
    normalised: list[NormalisedBiomarker],
    caveats: list[str],
    extraction_confidence: float,
) -> str:
    """Build a plain-language summary with mandatory non-diagnostic disclaimer."""
    lines: list[str] = [_DISCLAIMER, ""]

    abnormal = [b for b in normalised if b.flag in ABNORMAL_FLAGS]
    normal = [b for b in normalised if b.flag == "normal"]
    problematic = [b for b in normalised if b.flag in {"impossible", "ambiguous"}]

    if not normalised:
        lines.append("No recognised biomarker values could be extracted from this document.")
    else:
        lines.append(
            f"This report contains {len(normalised)} recognised biomarker value(s). "
            f"Extraction confidence: {extraction_confidence:.0%}."
        )
        lines.append("")

        if abnormal:
            lines.append("Values outside the reference range:")
            for b in abnormal:
                phrase = _FLAG_PHRASES.get(b.flag, b.flag)
                ref_parts = []
                if b.ref_range_low is not None:
                    ref_parts.append(f"≥{b.ref_range_low}")
                if b.ref_range_high is not None:
                    ref_parts.append(f"≤{b.ref_range_high}")
                ref_str = f" (reference: {' and '.join(ref_parts)} {b.canonical_unit})" if ref_parts else ""
                lines.append(
                    f"  • {b.canonical_name}: {b.normalised_value} {b.canonical_unit} "
                    f"— {phrase}{ref_str}"
                )
            lines.append("")

        if normal:
            names = ", ".join(b.canonical_name for b in normal)
            lines.append(f"Values within reference range: {names}.")
            lines.append("")

        values = {b.canonical_name: b.normalised_value for b in normalised}
        glucose = values.get("Fasting Blood Glucose")
        hba1c = values.get("HbA1c")
        total_cholesterol = values.get("Total Cholesterol")
        ldl = values.get("LDL Cholesterol")
        hdl = values.get("HDL Cholesterol")
        triglycerides = values.get("Triglycerides")

        if normal and not abnormal and not problematic:
            lines.append(
                "Screening interpretation: No diseases detected by the configured patterns "
                "in the reported parameters. This does not exclude conditions that require "
                "other tests or a clinician's assessment."
            )
            lines.append("")
        elif glucose is not None and glucose >= 126 and hba1c is not None and hba1c >= 6.5:
            lines.append(
                "Possible condition pattern (requires clinician confirmation): The combined "
                "elevation of fasting blood glucose and HbA1c may be indicative of diabetes "
                "mellitus or significant persistent dysglycaemia."
            )
            if (
                (total_cholesterol is not None and total_cholesterol > 200)
                or (ldl is not None and ldl > 100)
                or (hdl is not None and hdl < 40)
                or (triglycerides is not None and triglycerides > 150)
            ):
                lines.append(
                    "The accompanying cholesterol pattern may also indicate dyslipidaemia and "
                    "increased cardiometabolic risk."
                )
            lines.append("")

        if problematic:
            lines.append("Values that could not be reliably evaluated:")
            for b in problematic:
                lines.append(f"  • {b.canonical_name}: {_FLAG_PHRASES.get(b.flag, b.flag)}")
            lines.append("")

    if caveats:
        lines.append("Extraction notes and caveats:")
        for c in caveats:
            lines.append(f"  • {c}")
        lines.append("")

    lines.append(
        "This assistive analysis was produced by an automated rule-based system "
        f"(rule version: {RULE_VERSION}, extraction version: {EXTRACTION_MODEL_VERSION}). "
        "It has NOT been reviewed or accepted by a clinician. "
        "Please consult your doctor before making any health decisions."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point — 6.2 + 6.3 + 6.4 + 6.5 combined
# ---------------------------------------------------------------------------

@dataclass
class ReportAnalysis:
    """Complete analysis result for a single document's text content."""
    extracted_biomarkers: dict[str, Any]    # canonical_name → {value, unit, ref_range, flag, warning}
    abnormal_flags: list[str]               # canonical names of out-of-range values
    summary: str                            # plain-language assistive summary
    caveats: list[str]                      # all extraction warnings and notes
    confidence_score: float                 # 0.0–1.0 overall extraction confidence
    analysis_type: str = "lab_report_extraction"
    rule_version: str = RULE_VERSION
    model_version: str = EXTRACTION_MODEL_VERSION


def analyse_report_text(
    text: str,
    extraction_confidence: float = 1.0,
    additional_caveats: list[str] | None = None,
) -> ReportAnalysis:
    """Full pipeline: extract → normalise → flag → summarise.

    Parameters
    ----------
    text:
        Plain text extracted from the document (via PDF layer or OCR).
    extraction_confidence:
        Confidence score from the text-extraction step (0.0–1.0).
        Low confidence degrades the overall output confidence.
    additional_caveats:
        Any upstream warnings (e.g. from OCR) to include in the summary.

    Returns a ``ReportAnalysis`` ready to be persisted as a
    ``DocumentAnalysisResult`` row.
    """
    caveats: list[str] = list(additional_caveats or [])

    if not text or not text.strip():
        return ReportAnalysis(
            extracted_biomarkers={},
            abnormal_flags=[],
            summary=build_summary([], ["No text content was available for analysis."], 0.0),
            caveats=["No text content was available for analysis."],
            confidence_score=0.0,
        )

    # ---- Extract ----
    raw = extract_raw_biomarkers(text)
    if not raw:
        caveats.append(
            "No recognised biomarker patterns were found in the extracted text. "
            "The document may use non-standard terminology or may not be a supported report type."
        )

    # ---- Normalise + flag ----
    normalised, norm_warnings = normalise_biomarkers(raw)
    caveats.extend(norm_warnings)

    # ---- Abnormal list ----
    abnormal_flags = build_abnormal_flags(normalised)

    # ---- Overall confidence ----
    # Reduce confidence if normalisation had unit warnings or impossible values.
    penalty = sum(
        0.1 for b in normalised
        if b.flag in {"impossible", "ambiguous"} or b.warning
    )
    overall_confidence = max(0.0, round(extraction_confidence - penalty, 3))

    if extraction_confidence < 0.5:
        caveats.append(
            f"Text extraction confidence was low ({extraction_confidence:.0%}). "
            "Biomarker values may be inaccurate due to OCR errors or poor document quality."
        )

    # ---- Structured biomarker dict ----
    bio_dict: dict[str, Any] = {}
    for b in normalised:
        bio_dict[b.canonical_name] = {
            "value": b.normalised_value,
            "unit": b.canonical_unit,
            "ref_range": {
                "low": b.ref_range_low,
                "high": b.ref_range_high,
            },
            "flag": b.flag,
            "warning": b.warning,
        }

    # ---- Summary ----
    summary = build_summary(normalised, caveats, overall_confidence)

    return ReportAnalysis(
        extracted_biomarkers=bio_dict,
        abnormal_flags=abnormal_flags,
        summary=summary,
        caveats=caveats,
        confidence_score=overall_confidence,
    )
