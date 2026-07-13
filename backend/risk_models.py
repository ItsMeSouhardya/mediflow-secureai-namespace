"""Versioned disease-risk inference engine — decision support only.

Covers task 6.7 through 6.11:
  6.7  Validated initial model scope: diabetes risk and cardiovascular risk
  6.8  Validated prediction input schemas and range checks
  6.9  Prediction models behind a versioned inference interface
  6.10 Return probability/risk band, contributing factors, model version,
       and limitations
  6.11 Store prediction input snapshots, outputs, model version, timestamp,
       and reviewer status (via RiskPrediction model in models.py)

DESIGN CONSTRAINTS
------------------
- All outputs carry mandatory non-diagnostic disclaimers.
- Probability values are decision-support estimates, NOT diagnostic probabilities.
- Every prediction is stored as an immutable snapshot (input + output + version).
- Model version strings must change whenever the scoring logic changes.
- No patient identifiers are accepted by the inference functions — the
  caller passes only de-identified numeric inputs.
- Reviewer status starts as "pending"; a doctor must explicitly accept before
  any clinical use is permitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

DIABETES_MODEL_VERSION = "diabetes-risk-v1.0"
CARDIO_MODEL_VERSION = "cardio-risk-v1.0"

_NON_DIAGNOSTIC_DISCLAIMER = (
    "IMPORTANT: This risk estimate is for informational and decision-support "
    "purposes ONLY. It is NOT a diagnosis, NOT a clinical recommendation, and "
    "must NOT be used as a substitute for professional medical evaluation. "
    "All results require review by a qualified healthcare professional before "
    "any clinical action is taken."
)

# ---------------------------------------------------------------------------
# 6.8 — Validated input schemas (pure dataclasses; Pydantic used at API layer)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DiabetesRiskInput:
    """Inputs for the diabetes-risk model.

    All values must pass range checks before inference runs.
    Ages outside 18–100 and any obviously impossible value raise ValueError.
    """
    age: float                     # years  18–100
    bmi: float                     # kg/m²  10–70
    fasting_glucose: float         # mg/dL  50–500
    hba1c: float | None = None     # %      3–15  (optional)
    family_history_diabetes: bool = False
    hypertension: bool = False
    physical_activity_low: bool = False  # True = sedentary / low activity

    def __post_init__(self) -> None:
        _check("age", self.age, 18, 100)
        _check("bmi", self.bmi, 10, 70)
        _check("fasting_glucose", self.fasting_glucose, 50, 500)
        if self.hba1c is not None:
            _check("hba1c", self.hba1c, 3, 15)


@dataclass(frozen=True)
class CardiovascularRiskInput:
    """Inputs for the cardiovascular-risk model.

    Based on a simplified Framingham-inspired scoring approach.
    """
    age: float               # years  18–100
    systolic_bp: float       # mmHg   70–250
    total_cholesterol: float # mg/dL  50–500
    hdl_cholesterol: float   # mg/dL  10–200
    smoker: bool = False
    diabetes: bool = False
    hypertension_treatment: bool = False

    def __post_init__(self) -> None:
        _check("age", self.age, 18, 100)
        _check("systolic_bp", self.systolic_bp, 70, 250)
        _check("total_cholesterol", self.total_cholesterol, 50, 500)
        _check("hdl_cholesterol", self.hdl_cholesterol, 10, 200)


def _check(name: str, value: float, lo: float, hi: float) -> None:
    if not (lo <= value <= hi):
        raise ValueError(
            f"Input '{name}' value {value} is outside the valid range [{lo}, {hi}]. "
            "Verify the value before requesting a prediction."
        )


# ---------------------------------------------------------------------------
# 6.10 — Prediction output
# ---------------------------------------------------------------------------

@dataclass
class RiskPredictionOutput:
    """Structured output from any risk model."""
    model_version: str
    risk_score: float                      # 0.0–1.0 raw probability estimate
    risk_band: str                         # "low" | "moderate" | "high" | "very_high"
    contributing_factors: list[str]        # human-readable factor descriptions
    protective_factors: list[str]          # human-readable protective factors
    limitations: list[str]                 # model limitations and caveats
    disclaimer: str = field(default=_NON_DIAGNOSTIC_DISCLAIMER)
    input_snapshot: dict[str, Any] = field(default_factory=dict)


def _risk_band(score: float) -> str:
    if score < 0.10:
        return "low"
    if score < 0.20:
        return "moderate"
    if score < 0.35:
        return "high"
    return "very_high"


# ---------------------------------------------------------------------------
# 6.9 — Diabetes risk model (v1.0)
#
# Approach: points-based system derived from the ADA risk test and FINDRISC
# scale, adapted for the available inputs.  This is a simplified heuristic
# model for demonstration — it has NOT been validated on clinical populations.
# ---------------------------------------------------------------------------

_DIABETES_LIMITATIONS = [
    "This is a simplified points-based heuristic model, not a validated clinical tool.",
    "It has not been validated on the target population.",
    "It does not account for ethnicity, gestational history, or medication effects.",
    "A normal score does not rule out diabetes; an elevated score requires clinical testing.",
    "Model version: " + DIABETES_MODEL_VERSION,
]


def predict_diabetes_risk(inp: DiabetesRiskInput) -> RiskPredictionOutput:
    """Estimate diabetes risk using a points-based heuristic.

    Score is converted to a probability estimate via a logistic-like mapping
    solely for a consistent 0–1 output range.  It is NOT a true probability.
    """
    points = 0
    factors: list[str] = []
    protective: list[str] = []

    # Age
    if inp.age >= 65:
        points += 4
        factors.append("Age ≥ 65 years")
    elif inp.age >= 55:
        points += 3
        factors.append("Age 55–64 years")
    elif inp.age >= 45:
        points += 2
        factors.append("Age 45–54 years")
    else:
        protective.append("Age < 45 years")

    # BMI
    if inp.bmi >= 35:
        points += 5
        factors.append(f"BMI {inp.bmi:.1f} kg/m² (obese class II+)")
    elif inp.bmi >= 30:
        points += 4
        factors.append(f"BMI {inp.bmi:.1f} kg/m² (obese class I)")
    elif inp.bmi >= 25:
        points += 2
        factors.append(f"BMI {inp.bmi:.1f} kg/m² (overweight)")
    else:
        protective.append(f"BMI {inp.bmi:.1f} kg/m² (normal range)")

    # Fasting glucose
    if inp.fasting_glucose >= 126:
        points += 6
        factors.append(f"Fasting glucose {inp.fasting_glucose:.0f} mg/dL — diabetic range (≥126)")
    elif inp.fasting_glucose >= 100:
        points += 4
        factors.append(f"Fasting glucose {inp.fasting_glucose:.0f} mg/dL — pre-diabetic range (100–125)")
    else:
        protective.append(f"Fasting glucose {inp.fasting_glucose:.0f} mg/dL (normal)")

    # HbA1c (optional)
    if inp.hba1c is not None:
        if inp.hba1c >= 6.5:
            points += 5
            factors.append(f"HbA1c {inp.hba1c:.1f}% — diabetic range (≥6.5%)")
        elif inp.hba1c >= 5.7:
            points += 3
            factors.append(f"HbA1c {inp.hba1c:.1f}% — pre-diabetic range (5.7–6.4%)")
        else:
            protective.append(f"HbA1c {inp.hba1c:.1f}% (normal)")

    # Family history
    if inp.family_history_diabetes:
        points += 3
        factors.append("Family history of diabetes")

    # Hypertension
    if inp.hypertension:
        points += 2
        factors.append("Diagnosed hypertension")

    # Physical activity
    if inp.physical_activity_low:
        points += 2
        factors.append("Low physical activity / sedentary lifestyle")
    else:
        protective.append("Adequate physical activity")

    # Map points to 0–1 via linear scaling (max theoretical ~27 points)
    max_points = 27
    raw_score = round(min(points / max_points, 1.0), 4)

    return RiskPredictionOutput(
        model_version=DIABETES_MODEL_VERSION,
        risk_score=raw_score,
        risk_band=_risk_band(raw_score),
        contributing_factors=factors,
        protective_factors=protective,
        limitations=_DIABETES_LIMITATIONS,
        input_snapshot={
            "age": inp.age,
            "bmi": inp.bmi,
            "fasting_glucose": inp.fasting_glucose,
            "hba1c": inp.hba1c,
            "family_history_diabetes": inp.family_history_diabetes,
            "hypertension": inp.hypertension,
            "physical_activity_low": inp.physical_activity_low,
        },
    )


# ---------------------------------------------------------------------------
# 6.9 — Cardiovascular risk model (v1.0)
#
# Simplified Framingham-inspired 10-year CVD risk heuristic.
# Uses point scoring; NOT the full Cox regression model.
# ---------------------------------------------------------------------------

_CARDIO_LIMITATIONS = [
    "This is a simplified Framingham-inspired heuristic, not the validated full model.",
    "It uses a points-based approximation and has not been validated on this population.",
    "It does not account for LDL, triglycerides, CRP, family history, or renal function.",
    "A low score does not rule out cardiovascular disease.",
    "Consult a cardiologist for formal 10-year CVD risk assessment.",
    "Model version: " + CARDIO_MODEL_VERSION,
]


def predict_cardiovascular_risk(inp: CardiovascularRiskInput) -> RiskPredictionOutput:
    """Estimate 10-year cardiovascular risk using a simplified heuristic."""
    points = 0
    factors: list[str] = []
    protective: list[str] = []

    # Age
    if inp.age >= 70:
        points += 6
        factors.append("Age ≥ 70 years")
    elif inp.age >= 60:
        points += 4
        factors.append("Age 60–69 years")
    elif inp.age >= 50:
        points += 3
        factors.append("Age 50–59 years")
    elif inp.age >= 40:
        points += 2
        factors.append("Age 40–49 years")
    else:
        protective.append("Age < 40 years")

    # Systolic BP
    if inp.systolic_bp >= 160:
        points += 5
        factors.append(f"Systolic BP {inp.systolic_bp:.0f} mmHg (stage 2 hypertension)")
    elif inp.systolic_bp >= 140:
        points += 3
        factors.append(f"Systolic BP {inp.systolic_bp:.0f} mmHg (stage 1 hypertension)")
    elif inp.systolic_bp >= 130:
        points += 2
        factors.append(f"Systolic BP {inp.systolic_bp:.0f} mmHg (elevated)")
    else:
        protective.append(f"Systolic BP {inp.systolic_bp:.0f} mmHg (normal)")

    # Total cholesterol
    if inp.total_cholesterol >= 240:
        points += 4
        factors.append(f"Total cholesterol {inp.total_cholesterol:.0f} mg/dL (high)")
    elif inp.total_cholesterol >= 200:
        points += 2
        factors.append(f"Total cholesterol {inp.total_cholesterol:.0f} mg/dL (borderline high)")
    else:
        protective.append(f"Total cholesterol {inp.total_cholesterol:.0f} mg/dL (desirable)")

    # HDL (protective)
    if inp.hdl_cholesterol < 40:
        points += 4
        factors.append(f"HDL {inp.hdl_cholesterol:.0f} mg/dL (low — major risk factor)")
    elif inp.hdl_cholesterol < 60:
        points += 1
        factors.append(f"HDL {inp.hdl_cholesterol:.0f} mg/dL (below optimal)")
    else:
        points -= 1
        protective.append(f"HDL {inp.hdl_cholesterol:.0f} mg/dL (protective)")

    # Smoking
    if inp.smoker:
        points += 4
        factors.append("Current smoker")
    else:
        protective.append("Non-smoker")

    # Diabetes
    if inp.diabetes:
        points += 3
        factors.append("Diagnosed diabetes")

    # Hypertension treatment
    if inp.hypertension_treatment:
        points += 1
        factors.append("On antihypertensive medication")

    max_points = 27
    raw_score = round(max(0.0, min(points / max_points, 1.0)), 4)

    return RiskPredictionOutput(
        model_version=CARDIO_MODEL_VERSION,
        risk_score=raw_score,
        risk_band=_risk_band(raw_score),
        contributing_factors=factors,
        protective_factors=protective,
        limitations=_CARDIO_LIMITATIONS,
        input_snapshot={
            "age": inp.age,
            "systolic_bp": inp.systolic_bp,
            "total_cholesterol": inp.total_cholesterol,
            "hdl_cholesterol": inp.hdl_cholesterol,
            "smoker": inp.smoker,
            "diabetes": inp.diabetes,
            "hypertension_treatment": inp.hypertension_treatment,
        },
    )


# ---------------------------------------------------------------------------
# Versioned inference interface (6.9)
# ---------------------------------------------------------------------------

SUPPORTED_MODELS = {
    "diabetes_risk": {
        "version": DIABETES_MODEL_VERSION,
        "description": "Simplified diabetes risk estimate based on age, BMI, glucose, HbA1c, and lifestyle factors.",
        "input_type": "DiabetesRiskInput",
        "limitations": _DIABETES_LIMITATIONS,
    },
    "cardiovascular_risk": {
        "version": CARDIO_MODEL_VERSION,
        "description": "Simplified 10-year cardiovascular risk estimate based on Framingham-inspired scoring.",
        "input_type": "CardiovascularRiskInput",
        "limitations": _CARDIO_LIMITATIONS,
    },
}


def run_prediction(model_name: str, inputs: dict[str, Any]) -> RiskPredictionOutput:
    """Versioned inference entry point.

    Parameters
    ----------
    model_name:
        One of the keys in SUPPORTED_MODELS.
    inputs:
        Raw dict of input values (validated and converted to the appropriate
        input dataclass inside this function).

    Raises ValueError for unknown model names or invalid inputs.
    """
    if model_name == "diabetes_risk":
        inp = DiabetesRiskInput(**{k: v for k, v in inputs.items() if k in DiabetesRiskInput.__dataclass_fields__})
        return predict_diabetes_risk(inp)

    if model_name == "cardiovascular_risk":
        inp = CardiovascularRiskInput(**{k: v for k, v in inputs.items() if k in CardiovascularRiskInput.__dataclass_fields__})
        return predict_cardiovascular_risk(inp)

    raise ValueError(
        f"Unknown model '{model_name}'. Supported models: {list(SUPPORTED_MODELS)}"
    )
