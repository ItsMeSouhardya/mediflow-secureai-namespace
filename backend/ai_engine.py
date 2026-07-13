"""Deterministic queue and prototype clinical decision-support calculations.

The module is database-agnostic: callers provide a repository. No function opens
database connections or commits transactions.

Task 6.13 / 6.14 — Emergency symptom analysis policy
------------------------------------------------------
``analyze_patient()`` uses CONSERVATIVE escalation:
- Any mention of chest pain, breathing difficulty, stroke signs, major bleeding,
  or unconsciousness is escalated to Emergency regardless of severity_score.
- Threshold for Urgent escalation is kept low (score ≥ 3) to avoid under-triage.
- Every call-site that surfaces the result to a patient MUST include the
  non-diagnostic disclaimer returned in the ``AnalysisResult`` namedtuple.
- This function is decision-support only; it does NOT produce a diagnosis.
"""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from repository import MediFlowRepository


# ---------------------------------------------------------------------------
# 6.14 — Non-diagnostic disclaimer (must accompany every AI output to users)
# ---------------------------------------------------------------------------

EMERGENCY_AI_DISCLAIMER = (
    "IMPORTANT: This automated assessment is for informational purposes ONLY. "
    "It is NOT a medical diagnosis. If you are experiencing a medical emergency, "
    "call emergency services (112 / 911) IMMEDIATELY — do not wait for this system. "
    "Always consult a qualified healthcare professional for any health concerns."
)

EMERGENCY_SERVICE_GUIDANCE = (
    "If you or someone nearby is experiencing chest pain, difficulty breathing, "
    "signs of stroke (face drooping, arm weakness, speech difficulty), loss of "
    "consciousness, or severe bleeding — call emergency services NOW (112 / 911). "
    "Do not drive yourself. Time is critical."
)


def get_wait_info(repo: MediFlowRepository, dept_id: int):
    queue_len = repo.waiting_count(dept_id)
    consult_time = repo.department_consult_time(dept_id)
    wait_time = queue_len * consult_time

    current_hour = datetime.now().hour
    if 11 <= current_hour <= 14:
        wait_time += 15
    elif 18 <= current_hour <= 20:
        wait_time += 10

    advice = f"Delay your visit by {wait_time // 2} minutes" if wait_time > 45 else "You can visit now"
    return wait_time, advice, queue_len, consult_time


def get_crowd_and_timing(repo: MediFlowRepository, dept_id: int):
    peak_hour = repo.peak_hour(dept_id)
    count = repo.waiting_count(dept_id)
    if count < 3:
        crowd, crowd_color = "Low", "green"
    elif count <= 7:
        crowd, crowd_color = "Moderate", "yellow"
    else:
        crowd, crowd_color = "High", "red"
    suggestion = "Visit after 2 PM" if peak_hour == "11AM-1PM" else "Morning hours are better"
    return peak_hour, crowd, suggestion, crowd_color


def suggest_doctor(repo: MediFlowRepository, dept_id: int | None = None):
    if dept_id:
        doctors = repo.available_doctors(dept_id)
        if doctors:
            return doctors[0].doctor_name
    return "Doctor assignment pending"


def reentry_message():
    return "If you missed your token, you can rejoin with adjusted priority."


def hospital_journey(repo: MediFlowRepository, dept_id: int, wait_time: int):
    consult_time = repo.department_consult_time(dept_id)
    total_time = 5 + wait_time + consult_time + 10
    return [
        "Registration → 5 mins",
        f"Waiting → {wait_time} mins",
        f"Consultation → {consult_time} mins",
        "Pharmacy → 10 mins",
    ], total_time


class AnalysisResult(NamedTuple):
    """Structured output from analyze_patient() — always carries a disclaimer."""
    emergency: str          # "Emergency" | "Urgent" | "Normal"
    department: str         # suggested triage department
    hospital_status: str    # queue density label
    is_emergency: bool
    severity_score: int
    escalation_reason: str | None   # explains why Emergency was triggered
    disclaimer: str         # MUST be shown to the user
    emergency_guidance: str         # always shown alongside emergency results


# ---------------------------------------------------------------------------
# 6.13 — Conservative escalation keywords
#
# These symptoms are treated as unconditional Emergency regardless of the
# accumulated severity score.  Any ambiguity resolves in favour of escalation.
# ---------------------------------------------------------------------------

_UNCONDITIONAL_EMERGENCY: list[tuple[list[str], str]] = [
    (
        ["chest pain", "chest ache", "chest tightness", "chest pressure",
         "chest discomfort", "chest heaviness"],
        "Chest pain — possible cardiac emergency",
    ),
    (
        ["difficulty breathing", "can't breathe", "cannot breathe", "shortness of breath",
         "unable to breathe", "breathless", "dyspnea", "not breathing", "stopped breathing",
         "respiratory distress"],
        "Breathing difficulty — possible respiratory emergency",
    ),
    (
        ["stroke", "facial droop", "face drooping", "arm weakness", "sudden numbness",
         "slurred speech", "sudden confusion", "sudden vision loss", "sudden severe headache",
         "loss of balance", "paralysis"],
        "Stroke signs — time-critical neurological emergency",
    ),
    (
        ["unconscious", "unresponsive", "fainted", "collapsed", "not responding",
         "passed out", "loss of consciousness", "unaware", "no response"],
        "Loss of consciousness — immediate emergency",
    ),
    (
        ["severe bleeding", "major bleeding", "haemorrhage", "hemorrhage",
         "blood loss", "bleeding heavily", "bleeding profusely", "arterial bleed"],
        "Major bleeding — immediate emergency",
    ),
    (
        ["heart attack", "cardiac arrest", "myocardial infarction",
         "ventricular fibrillation", "cardiac emergency"],
        "Cardiac event — immediate emergency",
    ),
]

_URGENT_KEYWORDS: list[tuple[list[str], int]] = [
    (["high fever", "fever above 39", "temperature above 39", "high temperature", "pyrexia"], 3),
    (["severe pain", "extreme pain", "unbearable pain", "worst pain"], 3),
    (["vomiting blood", "blood in urine", "blood in stool", "coughing blood"], 4),
    (["seizure", "convulsion", "fit", "epileptic"], 4),
    (["allergic reaction", "anaphylaxis", "severe allergy", "throat swelling", "hives with breathing"], 4),
    (["fever", "high temperature"], 1),
    (["pain", "ache", "discomfort"], 1),
    (["nausea", "vomiting", "diarrhoea", "diarrhea"], 1),
    (["dizziness", "dizzy", "lightheaded", "vertigo"], 1),
    (["headache", "migraine"], 1),
    (["weakness", "fatigue", "tiredness"], 1),
    (["bleeding", "blood"], 2),
]


def analyze_patient(repo: MediFlowRepository, symptoms: str, dept_id: int) -> AnalysisResult:
    """Triage symptoms with CONSERVATIVE escalation policy (task 6.13).

    Rules
    -----
    1. If ANY unconditional-emergency keyword is present → Emergency, regardless
       of total score.  The first matching reason is returned.
    2. Otherwise, severity score is accumulated from urgent keywords.
    3. score ≥ 6 → Emergency; score ≥ 3 → Urgent; else → Normal.
    4. The result ALWAYS carries EMERGENCY_AI_DISCLAIMER and EMERGENCY_SERVICE_GUIDANCE.
    5. Department suggestion is independent of the escalation level.

    Returns an AnalysisResult namedtuple.
    """
    s = (symptoms or "").lower()
    escalation_reason: str | None = None
    is_emergency = False

    # ---- Rule 1: unconditional emergency check ----
    for keywords, reason in _UNCONDITIONAL_EMERGENCY:
        if any(kw in s for kw in keywords):
            is_emergency = True
            escalation_reason = reason
            break

    # ---- Rule 2: score-based escalation ----
    severity_score = 0
    if not is_emergency:
        for keywords, weight in _URGENT_KEYWORDS:
            if any(kw in s for kw in keywords):
                severity_score += weight
        if severity_score >= 6:
            is_emergency = True
            escalation_reason = f"Multiple high-severity symptoms (score {severity_score})"

    emergency_level = (
        "Emergency" if is_emergency
        else "Urgent" if severity_score >= 3
        else "Normal"
    )

    # ---- Department suggestion ----
    if any(k in s for k in ["bone", "fracture", "joint", "sprain", "orthopedic", "orthopaedic"]):
        department = "Orthopedic"
    elif any(k in s for k in ["heart", "chest", "cardiac", "cardio", "palpitation"]):
        department = "Cardiology"
    elif any(k in s for k in ["child", "infant", "baby", "pediatric", "paediatric"]):
        department = "Pediatrics"
    elif any(k in s for k in ["ear", "nose", "throat", " ent ", "sinus", "tonsil"]):
        department = "ENT"
    elif any(k in s for k in ["tooth", "dental", "gum", "mouth", "jaw"]):
        department = "Dental"
    elif any(k in s for k in ["skin", "rash", "itch", "derma", "allerg"]):
        department = "Dermatology"
    elif any(k in s for k in ["eye", "vision", "ophthal", "blur"]):
        department = "Ophthalmology"
    elif any(k in s for k in ["mental", "anxiety", "depression", "psychi", "stress disorder"]):
        department = "Psychiatry"
    elif any(k in s for k in ["stomach", "abdomen", "gastro", "bowel", "intestin", "liver"]):
        department = "Gastroenterology"
    elif any(k in s for k in ["urin", "kidney", "bladder", "nephro"]):
        department = "Nephrology / Urology"
    else:
        department = "General Medicine"

    count = repo.waiting_count(dept_id)
    status = "Very Busy" if count > 7 else "Moderate" if count > 3 else "Free"

    return AnalysisResult(
        emergency=emergency_level,
        department=department,
        hospital_status=status,
        is_emergency=is_emergency,
        severity_score=severity_score,
        escalation_reason=escalation_reason,
        disclaimer=EMERGENCY_AI_DISCLAIMER,
        emergency_guidance=EMERGENCY_SERVICE_GUIDANCE,
    )


def suggest_hospital(repo: MediFlowRepository, wait_time: int):
    options = repo.hospitals_for_suggestion()
    if not options:
        return {"options": [], "recommended": None}
    recommended = min(options, key=lambda option: option["wait_time"])
    return {"options": options, "recommended": recommended["name"]}


def elderly_mode(age: int):
    if age >= 60:
        return {
            "enabled": True,
            "benefits": ["Priority Queue", "Reduced Waiting Time", "Assistance Available"],
        }
    return {"enabled": False, "benefits": []}


def get_position(repo: MediFlowRepository, dept_id: int, token: str | None):
    return repo.queue_position(dept_id, token)


def compute_priority_score(age: int, symptoms: str, wait_time: int, emergency: str):
    score = 0
    if "emergency" in emergency.lower():
        score += 50
    if "urgent" in emergency.lower():
        score += 25
    if age >= 60:
        score += 20
    score += min(wait_time, 30)
    s = (symptoms or "").lower()
    if "chest pain" in s:
        score += 10
    if "breathing" in s:
        score += 8
    return score


def generate_ai_json(repo: MediFlowRepository, dept_id: int, token: str | None, symptoms: str, age: int):
    wait_time, advice, queue_len, consult_time = get_wait_info(repo, dept_id)
    position = get_position(repo, dept_id, token) if token else -1
    if position >= 0:
        # Convert the internal 1-based position into the patient-facing number
        # of people ahead, then use that exact value for the ETA.
        position = max(position - 1, 0)
        wait_time = position * consult_time
        advice = f"Delay your visit by {wait_time // 2} minutes" if wait_time > 45 else "You can visit now"
    peak, crowd, best_time, _ = get_crowd_and_timing(repo, dept_id)
    doctor = suggest_doctor(repo, dept_id)
    result = analyze_patient(repo, symptoms, dept_id)
    journey_list, total_time = hospital_journey(repo, dept_id, wait_time)
    advice = (
        "You can visit now to hospital"
        if total_time < 30
        else f"Delay your visit by {total_time - 30} mins"
    )
    return {
        "wait_time": wait_time,
        "advice": advice,
        "peak_hour": peak,
        "crowd": crowd,
        "best_time": best_time,
        "doctor": doctor,
        "emergency": result.emergency,
        "is_emergency": result.is_emergency,
        "department": result.department,
        "hospital_status": result.hospital_status,
        "escalation_reason": result.escalation_reason,
        "disclaimer": result.disclaimer,
        "emergency_guidance": result.emergency_guidance,
        "elderly_mode": elderly_mode(age),
        "journey": journey_list,
        "total_time": total_time,
        "hospital_alternative": suggest_hospital(repo, wait_time),
        "explanation": f"{queue_len} patients in queue × {consult_time} mins consultation",
        "position": position,
        "priority_score": compute_priority_score(age, symptoms, wait_time, result.emergency),
        "queue_length": queue_len,
        "consult_time": consult_time,
    }


def get_dashboard_stats(repo: MediFlowRepository, hospital_id: int = 1):
    return repo.dashboard_stats(hospital_id)
