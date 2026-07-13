"""Database repository used by API services and the AI calculation layer."""

from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from models import (
    Appointment,
    Department,
    Doctor,
    EmergencyCase,
    Feedback,
    Hospital,
    PatientProfile,
    QueueLog,
    QueueSession,
    SymptomsHistory,
    Token,
    User,
)


class MediFlowRepository:
    def __init__(self, session: Session):
        self.session = session

    # ---- Queue/AI reads -------------------------------------------------
    def prototype_background_waiting(self, dept_id: int, queue_date: date | None = None) -> int:
        """Return a stable daily crowd while no admin-operated queue exists."""
        day = queue_date or datetime.now(timezone.utc).date()
        return 2 + ((day.toordinal() * 5 + dept_id * 11) % 7)

    def waiting_count(self, dept_id: int) -> int:
        recorded = int(
            self.session.scalar(
                select(func.count(Token.token_id)).where(
                    Token.dept_id == dept_id,
                    Token.queue_date == datetime.now(timezone.utc).date(),
                    Token.status == "waiting",
                )
            )
            or 0
        )
        return recorded + self.prototype_background_waiting(dept_id)

    def department_consult_time(self, dept_id: int) -> int:
        return int(
            self.session.scalar(select(Department.avg_consult_time).where(Department.dept_id == dept_id)) or 10
        )

    def peak_hour(self, dept_id: int) -> str:
        row = self.session.execute(
            select(QueueLog.peak_hour, func.sum(QueueLog.total_patients).label("patients"))
            .where(QueueLog.dept_id == dept_id)
            .group_by(QueueLog.peak_hour)
            .order_by(func.sum(QueueLog.total_patients).desc())
            .limit(1)
        ).first()
        return row.peak_hour if row and row.peak_hour else "N/A"

    def available_doctors(self, dept_id: int) -> list[Doctor]:
        return list(
            self.session.scalars(
                select(Doctor)
                .where(Doctor.dept_id == dept_id, Doctor.availability == "Available")
                .order_by(Doctor.patients_today.asc(), Doctor.doctor_id.asc())
            )
        )

    def queue_position(self, dept_id: int, token_number: str | None) -> int:
        if not token_number:
            return -1
        token = self.session.scalar(
            select(Token)
            .where(Token.dept_id == dept_id, Token.token_number == token_number)
            .order_by(Token.queue_date.desc(), Token.created_at.desc())
            .limit(1)
        )
        if token is None or token.status != "waiting":
            return -1
        recorded_position = self.queue_position_v2(dept_id, token.token_id)
        if recorded_position < 0:
            return -1
        return recorded_position + self.prototype_background_waiting(dept_id, token.queue_date)

    def hospitals_for_suggestion(self) -> list[dict]:
        hospitals = list(self.session.scalars(select(Hospital).order_by(Hospital.hospital_id)))
        result = []
        for hospital in hospitals:
            waiting = int(
                self.session.scalar(
                    select(func.count(Token.token_id)).where(
                        Token.hospital_id == hospital.hospital_id,
                        Token.queue_date == datetime.now(timezone.utc).date(),
                        Token.status == "waiting",
                    )
                )
                or 0
            )
            result.append(
                {
                    "hospital_id": hospital.hospital_id,
                    "name": hospital.hospital_name,
                    "wait_time": waiting * 12,
                }
            )
        return result

    # ---- Core records ---------------------------------------------------
    def get_department(self, dept_id: int) -> Department | None:
        return self.session.get(Department, dept_id)

    def get_hospital(self, hospital_id: int) -> Hospital | None:
        return self.session.get(Hospital, hospital_id)

    def get_token(self, token_value: str) -> Token | None:
        if token_value.isdigit():
            return self.session.get(Token, int(token_value))
        return self.session.scalar(
            select(Token).where(Token.token_number == token_value).order_by(Token.created_at.desc()).limit(1)
        )

    def get_token_by_tracking_hash(self, tracking_code_hash: str) -> Token | None:
        return self.session.scalar(select(Token).where(Token.tracking_code_hash == tracking_code_hash).limit(1))

    def public_token_payload(self, token: Token) -> dict:
        hospital = self.get_hospital(token.hospital_id)
        department = self.get_department(token.dept_id)
        position = max(self.queue_position(token.dept_id, token.token_number) - 1, 0)
        return {
            "display_token": token.token_number,
            "status": token.status,
            "priority": token.priority,
            "position": position,
            "wait_time": position * (department.avg_consult_time if department else 10),
            "hospital_name": hospital.hospital_name if hospital else None,
            "department_name": department.dept_name if department else None,
            "estimated_time": token.estimated_time.isoformat() if token.estimated_time else None,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def token_payload(self, token: Token) -> dict:
        hospital = self.get_hospital(token.hospital_id)
        user = self.session.get(User, token.user_id)
        payload = token.to_dict()
        payload.update(
            {
                "token_code": token.token_number,
                "patient_name": user.name if user else None,
                "age": user.age if user else None,
                "hospital_name": hospital.hospital_name if hospital else None,
                "position": max(self.queue_position(token.dept_id, token.token_number) - 1, 0),
            }
        )
        return payload

    def get_or_create_user(self, name: str, age: int, phone: str | None, gender: str) -> User:
        """Only used for unauthenticated (legacy public) bookings.

        Authenticated bookings go directly through book_token(user_id=...) and
        never create a throwaway identity (13.1).
        """
        safe_phone = phone or f"prototype-{uuid.uuid4()}"
        user = self.session.scalar(select(User).where(User.phone == safe_phone))
        if user:
            user.name = name
            user.age = age
            user.gender = gender
            return user
        user = User(name=name, phone=safe_phone, age=age, gender=gender)
        self.session.add(user)
        self.session.flush()
        return user

    def get_or_create_patient_profile(self, user: User) -> PatientProfile:
        profile = self.session.scalar(select(PatientProfile).where(PatientProfile.user_id == user.user_id))
        if profile:
            return profile
        profile = PatientProfile(
            user_id=user.user_id,
            medical_record_number=f"MRN-{user.public_id.hex[:12].upper()}",
        )
        self.session.add(profile)
        self.session.flush()
        return profile

    def _allocate_queue_number(self, hospital_id: int, dept_id: int, queue_date: date) -> tuple[int, int]:
        # Fresh prototype databases should resemble an active hospital queue,
        # rather than visibly restarting at A001 on every run.
        initial_sequence = 20 + secrets.randbelow(141)
        if self.session.bind and self.session.bind.dialect.name == "postgresql":
            statement = (
                pg_insert(QueueSession)
                .values(
                    hospital_id=hospital_id,
                    dept_id=dept_id,
                    queue_date=queue_date,
                    next_sequence=initial_sequence + 1,
                    status="open",
                )
                .on_conflict_do_update(
                    constraint="uq_queue_session_day",
                    set_={"next_sequence": QueueSession.next_sequence + 1},
                )
                .returning(QueueSession.queue_session_id, QueueSession.next_sequence)
            )
            queue_session_id, next_sequence = self.session.execute(statement).one()
            return int(queue_session_id), int(next_sequence) - 1

        queue_session = self.session.scalar(
            select(QueueSession)
            .where(
                QueueSession.hospital_id == hospital_id,
                QueueSession.dept_id == dept_id,
                QueueSession.queue_date == queue_date,
            )
            .with_for_update()
        )
        if queue_session is None:
            queue_session = QueueSession(
                hospital_id=hospital_id,
                dept_id=dept_id,
                queue_date=queue_date,
                next_sequence=initial_sequence + 1,
                status="open",
            )
            self.session.add(queue_session)
            self.session.flush()
            return queue_session.queue_session_id, initial_sequence

        sequence = queue_session.next_sequence
        queue_session.next_sequence += 1
        self.session.flush()
        return queue_session.queue_session_id, sequence

    def book_token(
        self,
        *,
        dept_id: int,
        patient_name: str,
        age: int,
        phone: str | None,
        gender: str,
        symptoms: str,
        priority: str,
        doctor_id: int | None,
        user_id: int | None = None,
        tracking_code_hash: str | None = None,
        tracking_code_last4: str | None = None,
    ) -> Token:
        department = self.get_department(dept_id)
        if department is None:
            raise ValueError("Department not found")

        if user_id is not None:
            # Authenticated path (13.1) — use the real registered user and
            # their patient profile directly; never create a throwaway identity.
            user = self.session.get(User, user_id)
            if user is None:
                raise ValueError("Authenticated user not found")
            patient_profile = self.get_or_create_patient_profile(user)
        else:
            # Unauthenticated / legacy public path.
            user = self.get_or_create_user(patient_name, age, phone, gender)
            patient_profile = self.get_or_create_patient_profile(user)

        # 13.5 — prefer the least-loaded available doctor in this department
        # rather than accepting a random one from the caller (ai_engine now
        # delegates doctor selection here).
        if doctor_id is None:
            best_doctors = self.available_doctors(dept_id)
            doctor_id = best_doctors[0].doctor_id if best_doctors else None

        today = datetime.now(timezone.utc).date()
        queue_session_id, sequence = self._allocate_queue_number(department.hospital_id, dept_id, today)
        token = Token(
            user_id=user.user_id,
            patient_profile_id=patient_profile.patient_profile_id,
            hospital_id=department.hospital_id,
            dept_id=dept_id,
            doctor_id=doctor_id,
            queue_session_id=queue_session_id,
            queue_date=today,
            token_number=f"{chr(65 + ((dept_id - 1) % 26))}{sequence:03d}",
            tracking_code_hash=tracking_code_hash,
            tracking_code_last4=tracking_code_last4,
            status="waiting",
            priority=priority,
            booked_patient_name=patient_name,
            booked_patient_age=age,
            symptoms=symptoms,
        )
        self.session.add(token)
        self.session.flush()
        return token

    # ---- Lists/dashboards ----------------------------------------------
    def list_hospitals(self) -> list[dict]:
        rows = self.hospitals_for_suggestion()
        waits = [row["wait_time"] for row in rows]
        minimum = min(waits) if waits else 0
        hospitals: list[dict] = []
        for row in rows:
            hospital = self.get_hospital(row["hospital_id"])
            estimated_wait = row["wait_time"]
            hospitals.append(
                {
                    "hospital_id": hospital.hospital_id,
                    "name": hospital.hospital_name,
                    "address": hospital.location,
                    "emergency_available": hospital.emergency_available,
                    "busyness_level": hospital.busyness_level,
                    "base_wait": hospital.avg_wait_time,
                    "total_waiting": estimated_wait // 12,
                    "estimated_wait": estimated_wait,
                    "recommended": estimated_wait == minimum,
                    "status_color": "green" if estimated_wait < 30 else "yellow" if estimated_wait < 60 else "red",
                }
            )
        return hospitals

    def list_departments(self, hospital_id: int) -> list[dict]:
        departments = self.session.scalars(
            select(Department).where(Department.hospital_id == hospital_id).order_by(Department.dept_id)
        )
        return [{"dept_id": dept.dept_id, "name": dept.dept_name} for dept in departments]

    def departments_overview(self, hospital_id: int) -> list[dict]:
        departments = list(
            self.session.scalars(
                select(Department).where(Department.hospital_id == hospital_id).order_by(Department.dept_id)
            )
        )
        result = []
        for dept in departments:
            waiting = self.waiting_count(dept.dept_id)
            served = int(
                self.session.scalar(
                    select(func.count(Token.token_id)).where(
                        Token.dept_id == dept.dept_id,
                        Token.queue_date == datetime.now(timezone.utc).date(),
                        Token.status == "completed",
                    )
                )
                or 0
            )
            crowd, crowd_level = ("Crowded", "high") if waiting > 7 else ("Moderate", "medium") if waiting > 3 else ("Fast", "low")
            result.append(
                {
                    "dept_id": dept.dept_id,
                    "name": dept.dept_name,
                    "avg_consult_time": dept.avg_consult_time,
                    "waiting": waiting,
                    "served": served,
                    "wait_time": waiting * dept.avg_consult_time,
                    "crowd": crowd,
                    "crowd_level": crowd_level,
                }
            )
        return result

    def list_doctors(self, hospital_id: int) -> list[dict]:
        rows = self.session.execute(
            select(Doctor, Department.dept_name)
            .join(Department, Doctor.dept_id == Department.dept_id)
            .where(Department.hospital_id == hospital_id)
            .order_by(case((Doctor.availability == "Available", 0), else_=1), Doctor.doctor_name)
        )
        return [
            {
                "doctor_id": doctor.doctor_id,
                "name": doctor.doctor_name,
                "specialization": doctor.specialization,
                "patients_today": doctor.patients_today,
                "availability": doctor.availability,
                "department": department_name,
            }
            for doctor, department_name in rows
        ]

    def dashboard_stats(self, hospital_id: int) -> dict:
        total_waiting = int(
            self.session.scalar(
                select(func.count(Token.token_id)).where(
                    Token.hospital_id == hospital_id,
                    Token.queue_date == datetime.now(timezone.utc).date(),
                    Token.status == "waiting",
                )
            )
            or 0
        )
        total_served = int(
            self.session.scalar(
                select(func.count(Token.token_id)).where(
                    Token.hospital_id == hospital_id,
                    Token.queue_date == datetime.now(timezone.utc).date(),
                    Token.status == "completed",
                )
            )
            or 0
        )
        active_doctors = int(
            self.session.scalar(
                select(func.count(Doctor.doctor_id))
                .join(Department, Doctor.dept_id == Department.dept_id)
                .where(Department.hospital_id == hospital_id, Doctor.availability == "Available")
            )
            or 0
        )
        departments = []
        for row in self.departments_overview(hospital_id):
            department_doctors = int(
                self.session.scalar(
                    select(func.count(Doctor.doctor_id)).where(
                        Doctor.dept_id == row["dept_id"],
                        Doctor.availability == "Available",
                    )
                )
                or 0
            )
            hourly_slots = max(department_doctors, 1) * max(1, 60 // max(row["avg_consult_time"], 1))
            queue_capacity = max(10, hourly_slots)
            load_percentage = min(100, round((row["waiting"] / queue_capacity) * 100))
            crowd = "High" if row["waiting"] > 7 else "Moderate" if row["waiting"] > 3 else "Low"
            color = "red" if crowd == "High" else "yellow" if crowd == "Moderate" else "green"
            departments.append(
                {
                    "dept_id": row["dept_id"],
                    "name": row["name"],
                    "avg_consult_time": row["avg_consult_time"],
                    "waiting": row["waiting"],
                    "completed": row["served"],
                    "active_doctors": department_doctors,
                    "queue_capacity": queue_capacity,
                    "load_percentage": load_percentage,
                    "est_wait": row["wait_time"],
                    "crowd_level": crowd,
                    "crowd_color": color,
                    "peak_hour": self.peak_hour(row["dept_id"]),
                }
            )
        return {
            "total_waiting": total_waiting,
            "total_served": total_served,
            "active_doctors": active_doctors,
            "departments": departments,
        }

    # ---- Auxiliary CRUD -------------------------------------------------
    def symptoms_history(
        self,
        user_id: int | None = None,
        *,
        page: int = 1,
        per_page: int = 25,
        sort_order: str = "desc",
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[list[dict], int]:
        conditions = []
        if user_id:
            conditions.append(SymptomsHistory.user_id == user_id)
        if search:
            pattern = f"%{search}%"
            conditions.append(
                SymptomsHistory.symptoms.ilike(pattern)
                | SymptomsHistory.predicted_department.ilike(pattern)
            )
        if date_from:
            conditions.append(SymptomsHistory.visit_date >= date_from)
        if date_to:
            conditions.append(SymptomsHistory.visit_date <= date_to)
        total = int(
            self.session.scalar(select(func.count(SymptomsHistory.history_id)).where(*conditions)) or 0
        )
        order = SymptomsHistory.visit_date.asc() if sort_order == "asc" else SymptomsHistory.visit_date.desc()
        statement = (
            select(SymptomsHistory)
            .where(*conditions)
            .order_by(order, SymptomsHistory.history_id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return [row.to_dict() for row in self.session.scalars(statement)], total

    def add_symptoms_history(self, data: dict) -> SymptomsHistory:
        record = SymptomsHistory(
            user_id=data.get("user_id"),
            symptoms=data.get("symptoms"),
            severity_score=data.get("severity_score"),
            predicted_department=data.get("predicted_department"),
            visit_date=_parse_date(data.get("visit_date")) or date.today(),
        )
        self.session.add(record)
        self.session.flush()
        return record

    def emergency_cases(
        self,
        *,
        page: int = 1,
        per_page: int = 25,
        sort_order: str = "desc",
        search: str | None = None,
    ) -> tuple[list[dict], int]:
        conditions = []
        if search:
            pattern = f"%{search}%"
            conditions.append(
                EmergencyCase.emergency_level.ilike(pattern)
                | Token.token_number.ilike(pattern)
                | User.name.ilike(pattern)
            )
        total = int(
            self.session.scalar(
                select(func.count(EmergencyCase.case_id))
                .join(Token, EmergencyCase.token_id == Token.token_id)
                .join(User, Token.user_id == User.user_id)
                .where(*conditions)
            )
            or 0
        )
        order = EmergencyCase.case_id.asc() if sort_order == "asc" else EmergencyCase.case_id.desc()
        rows = self.session.execute(
            select(EmergencyCase, Token.token_number, User.name)
            .join(Token, EmergencyCase.token_id == Token.token_id)
            .join(User, Token.user_id == User.user_id)
            .where(*conditions)
            .order_by(order)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return [
            {**record.to_dict(), "token_number": token_number, "patient_name": patient_name}
            for record, token_number, patient_name in rows
        ], total

    def appointments(
        self,
        user_id: int | None = None,
        *,
        page: int = 1,
        per_page: int = 25,
        sort_order: str = "desc",
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[list[dict], int]:
        conditions = []
        if user_id:
            conditions.append(Appointment.user_id == user_id)
        if search:
            pattern = f"%{search}%"
            conditions.append(
                User.name.ilike(pattern)
                | Doctor.doctor_name.ilike(pattern)
                | Appointment.status.ilike(pattern)
            )
        if date_from:
            conditions.append(Appointment.appointment_date >= date_from)
        if date_to:
            conditions.append(Appointment.appointment_date <= date_to)
        total = int(
            self.session.scalar(
                select(func.count(Appointment.appointment_id))
                .join(User, Appointment.user_id == User.user_id)
                .join(Doctor, Appointment.doctor_id == Doctor.doctor_id)
                .where(*conditions)
            )
            or 0
        )
        primary_order = Appointment.appointment_date.asc() if sort_order == "asc" else Appointment.appointment_date.desc()
        statement = (
            select(Appointment, User.name, Doctor.doctor_name)
            .join(User, Appointment.user_id == User.user_id)
            .join(Doctor, Appointment.doctor_id == Doctor.doctor_id)
            .where(*conditions)
            .order_by(primary_order, Appointment.appointment_time)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return [
            {**appointment.to_dict(), "patient_name": patient_name, "doctor_name": doctor_name}
            for appointment, patient_name, doctor_name in self.session.execute(statement)
        ], total

    def add_appointment(self, data: dict) -> Appointment:
        user = self.session.get(User, int(data["user_id"]))
        if user is None:
            raise ValueError("User not found")
        patient_profile = self.get_or_create_patient_profile(user)
        appointment = Appointment(
            user_id=int(data["user_id"]),
            patient_profile_id=patient_profile.patient_profile_id,
            doctor_id=int(data["doctor_id"]),
            appointment_date=_parse_date(data.get("appointment_date")) or date.today(),
            appointment_time=_parse_time(data.get("appointment_time")) or time(9, 0),
            status=data.get("status", "Booked"),
        )
        self.session.add(appointment)
        self.session.flush()
        return appointment

    def feedback(
        self,
        *,
        page: int = 1,
        per_page: int = 25,
        sort_order: str = "desc",
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[list[dict], int]:
        conditions = []
        if search:
            pattern = f"%{search}%"
            conditions.append(Feedback.feedback_text.ilike(pattern) | User.name.ilike(pattern))
        if date_from:
            conditions.append(Feedback.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
        if date_to:
            conditions.append(Feedback.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
        total = int(
            self.session.scalar(
                select(func.count(Feedback.feedback_id))
                .join(User, Feedback.user_id == User.user_id)
                .where(*conditions)
            )
            or 0
        )
        order = Feedback.created_at.asc() if sort_order == "asc" else Feedback.created_at.desc()
        rows = self.session.execute(
            select(Feedback, User.name)
            .join(User, Feedback.user_id == User.user_id)
            .where(*conditions)
            .order_by(order)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return [{**feedback.to_dict(), "patient_name": name} for feedback, name in rows], total

    def add_feedback(self, data: dict) -> Feedback:
        feedback = Feedback(
            user_id=int(data["user_id"]),
            rating=int(data["rating"]),
            feedback_text=data.get("feedback_text"),
        )
        self.session.add(feedback)
        self.session.flush()
        return feedback

    # ---- 13.2 / 13.3 / 13.4 — Queue lifecycle -------------------------

    _PRIORITY_ORDER = {"emergency": 0, "elderly": 1, "normal": 2}

    def _priority_sort_key(self, token: "Token"):
        """Consistent priority ordering used everywhere (13.3 / 13.4)."""
        return (
            self._PRIORITY_ORDER.get(token.priority, 99),
            token.created_at,
            token.token_id,
        )

    def ordered_waiting_tokens(self, dept_id: int, queue_date: date | None = None) -> list["Token"]:
        """Return all waiting tokens in canonical priority order (13.3 / 13.4).

        Order: emergency → elderly → normal, then FIFO within each band.
        This is the single source of truth for queue ordering; every
        position/wait calculation calls this method.
        """
        day = queue_date or datetime.now(timezone.utc).date()
        tokens = list(
            self.session.scalars(
                select(Token)
                .where(Token.dept_id == dept_id, Token.queue_date == day, Token.status == "waiting")
                .order_by(
                    case(
                        (Token.priority == "emergency", 0),
                        (Token.priority == "elderly", 1),
                        else_=2,
                    ),
                    Token.created_at.asc(),
                    Token.token_id.asc(),
                )
            )
        )
        return tokens

    def queue_position_v2(self, dept_id: int, token_id: int) -> int:
        """Return 1-based priority-ordered position for a token (13.4)."""
        target = self.session.get(Token, token_id)
        if target is None:
            return -1
        tokens = self.ordered_waiting_tokens(dept_id, target.queue_date)
        for i, t in enumerate(tokens, 1):
            if t.token_id == token_id:
                return i
        return -1

    def wait_estimate(self, dept_id: int, token_id: int) -> int:
        """Estimate wait in minutes using queue position × consult_time ÷ active_doctors (13.7).

        Falls back to a simple position × consult_time when no active doctors
        are found (safe lower bound).
        """
        position = self.queue_position_v2(dept_id, token_id)
        if position < 0:
            return 0
        consult_time = self.department_consult_time(dept_id)
        active_doctors = max(
            int(
                self.session.scalar(
                    select(func.count(Doctor.doctor_id))
                    .join(Department, Doctor.dept_id == Department.dept_id)
                    .where(
                        Doctor.dept_id == dept_id,
                        Doctor.availability == "Available",
                    )
                )
                or 0
            ),
            1,  # avoid division by zero
        )
        return (position * consult_time) // active_doctors

    def get_next_waiting_token(self, dept_id: int) -> "Token | None":
        """Return the highest-priority waiting token for staff to call (13.2)."""
        tokens = self.ordered_waiting_tokens(dept_id)
        return tokens[0] if tokens else None

    def perform_queue_action(
        self,
        token: "Token",
        action: str,
        *,
        actor_user_id: int,
        session,
        reason: str | None = None,
    ) -> "Token":
        """Apply a lifecycle action to a queue token (13.2).

        Valid actions and their target statuses:
          call_next   → serving   (only from waiting)
          complete    → completed (only from serving)
          miss        → missed    (only from waiting or serving)
          requeue     → waiting   (from missed)
          cancel      → cancelled (from waiting or serving)
          transfer    → waiting   (keeps waiting, sets new dept — caller updates dept_id)

        Every action writes an AuditEvent row (13.2 audit).
        """
        from audit import write_audit_event

        transitions = {
            "call_next": ("waiting",   "serving"),
            "complete":  ("serving",   "completed"),
            "miss":      (None,        "missed"),     # None = any status
            "requeue":   ("missed",    "waiting"),
            "cancel":    (None,        "cancelled"),
        }

        if action not in transitions:
            from errors import ApiProblem
            raise ApiProblem(
                "invalid_queue_action",
                f"Unknown queue action '{action}'. "
                f"Valid actions: {sorted(transitions)}",
                400,
            )

        required_from, target_status = transitions[action]
        if required_from is not None and token.status != required_from:
            from errors import ApiProblem
            raise ApiProblem(
                "invalid_queue_state",
                f"Action '{action}' requires status '{required_from}' "
                f"(current: '{token.status}')",
                409,
            )

        old_status = token.status
        token.status = target_status

        write_audit_event(
            session,
            action=f"queue.{action}",
            resource_type="token",
            resource_id=token.token_id,
            actor_user_id=actor_user_id,
            details={
                "from_status": old_status,
                "to_status": target_status,
                "token_number": token.token_number,
                "dept_id": token.dept_id,
                "hospital_id": token.hospital_id,
                "reason": reason,
            },
        )
        session.flush()
        return token

    # ---- 13.5 — PostgreSQL-backed doctor/hospital recommendations ------

    def best_doctor_for_dept(self, dept_id: int) -> "Doctor | None":
        """Return the least-loaded available doctor for a department (13.5)."""
        doctors = self.available_doctors(dept_id)
        return doctors[0] if doctors else None

    def recommend_hospital(self, symptoms: str | None = None) -> dict:
        """Recommend the least-busy hospital based on live queue data (13.5).

        Returns a structured recommendation with wait time, status, and
        alternative options — replaces the random/hardcoded suggestion.
        """
        options = self.hospitals_for_suggestion()
        if not options:
            return {"options": [], "recommended": None}

        # Sort by live estimated wait (PostgreSQL-derived from waiting tokens).
        sorted_options = sorted(options, key=lambda h: h["wait_time"])
        recommended = sorted_options[0]

        return {
            "recommended": {
                "hospital_id": recommended["hospital_id"],
                "name": recommended["name"],
                "estimated_wait_minutes": recommended["wait_time"],
                "status": (
                    "Very Busy" if recommended["wait_time"] > 60
                    else "Moderate" if recommended["wait_time"] > 30
                    else "Available"
                ),
            },
            "options": [
                {
                    "hospital_id": o["hospital_id"],
                    "name": o["name"],
                    "estimated_wait_minutes": o["wait_time"],
                }
                for o in sorted_options
            ],
        }

    # ---- 13.10 — Admin resource overview --------------------------------

    def queue_overview(self, hospital_id: int) -> dict:
        """Full live queue overview for hospital-admin dashboard (13.10)."""
        depts = list(
            self.session.scalars(
                select(Department).where(Department.hospital_id == hospital_id)
                .order_by(Department.dept_id)
            )
        )
        dept_summaries = []
        total_waiting = 0
        total_serving = 0
        total_completed = 0

        for dept in depts:
            waiting_tokens = self.ordered_waiting_tokens(dept.dept_id)
            serving_count = int(
                self.session.scalar(
                    select(func.count(Token.token_id)).where(
                        Token.dept_id == dept.dept_id,
                        Token.status == "serving",
                    )
                ) or 0
            )
            completed_count = int(
                self.session.scalar(
                    select(func.count(Token.token_id)).where(
                        Token.dept_id == dept.dept_id,
                        Token.status == "completed",
                    )
                ) or 0
            )
            active_doctors = int(
                self.session.scalar(
                    select(func.count(Doctor.doctor_id)).where(
                        Doctor.dept_id == dept.dept_id,
                        Doctor.availability == "Available",
                    )
                ) or 0
            )
            waiting_count = len(waiting_tokens)
            total_waiting += waiting_count
            total_serving += serving_count
            total_completed += completed_count

            consult_time = dept.avg_consult_time
            est_wait = (waiting_count * consult_time) // max(active_doctors, 1)

            dept_summaries.append({
                "dept_id": dept.dept_id,
                "dept_name": dept.dept_name,
                "waiting": waiting_count,
                "serving": serving_count,
                "completed": completed_count,
                "active_doctors": active_doctors,
                "avg_consult_time": consult_time,
                "estimated_wait_minutes": est_wait,
                "priority_breakdown": {
                    "emergency": sum(1 for t in waiting_tokens if t.priority == "emergency"),
                    "elderly": sum(1 for t in waiting_tokens if t.priority == "elderly"),
                    "normal": sum(1 for t in waiting_tokens if t.priority == "normal"),
                },
                "next_token": waiting_tokens[0].token_number if waiting_tokens else None,
            })

        return {
            "hospital_id": hospital_id,
            "total_waiting": total_waiting,
            "total_serving": total_serving,
            "total_completed": total_completed,
            "departments": dept_summaries,
        }

    def list_waiting_tokens(self, dept_id: int) -> list[dict]:
        """Ordered list of waiting tokens for admin triage view (13.10)."""
        tokens = self.ordered_waiting_tokens(dept_id)
        result = []
        for pos, token in enumerate(tokens, 1):
            user = self.session.get(User, token.user_id)
            result.append({
                "position": pos,
                "token_id": token.token_id,
                "token_number": token.token_number,
                "priority": token.priority,
                "status": token.status,
                "patient_name": user.name if user else None,
                "created_at": token.created_at.isoformat(),
                "estimated_wait_minutes": (pos * self.department_consult_time(dept_id)) // max(
                    int(self.session.scalar(
                        select(func.count(Doctor.doctor_id)).where(
                            Doctor.dept_id == dept_id,
                            Doctor.availability == "Available",
                        )
                    ) or 0),
                    1,
                ),
            })
        return result


def _parse_date(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _parse_time(value) -> time | None:
    if value is None or isinstance(value, time):
        return value
    return time.fromisoformat(str(value))
