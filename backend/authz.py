"""CareRoute AI — context-aware authorization engine.

The single authority that decides what information any principal may access:

    Identity + Role + Relationship + Purpose + Permission + Clinical Context → Allowed Information

No endpoint and no AI feature may bypass this layer. The AI never decides access —
it only receives information this engine has already authorized.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from config import settings
from models import (
    Appointment, CaregiverPermission, CaregiverRelationship, CommunityAssignment,
    CommunityHealthWorker, Doctor, DoctorHospitalAffiliation, EmergencyAccessEvent,
    HospitalAdmin, HospitalStaff, Patient,
)

# ----------------------------------------------------------------- roles
ROLE_USER = "USER"
ROLE_CAREGIVER = "CAREGIVER"
ROLE_DOCTOR = "DOCTOR"
ROLE_STAFF = "STAFF"
ROLE_ADMIN = "ADMIN"
ROLE_CHW = "CHW"

ALL_ROLES = [ROLE_USER, ROLE_CAREGIVER, ROLE_DOCTOR, ROLE_STAFF, ROLE_ADMIN, ROLE_CHW]

# The nine grantable caregiver permissions (section 6 of the product spec).
CAREGIVER_PERMISSIONS = [
    "view_appointments", "request_appointments", "view_prescriptions",
    "view_medications", "view_health_logs", "assist_medication",
    "assist_navigation", "emergency_assist", "contact_emergency_person",
]

# Clinical-record access keys. Every role gets only what it needs (minimum necessary).
class Access:
    APPOINTMENTS = "appointments"
    PRESCRIPTIONS = "prescriptions"
    MEDICATIONS = "medications"
    HEALTH_LOGS = "health_logs"
    REPORTS = "reports"
    CONDITIONS = "conditions"
    ALLERGIES = "allergies"
    SNAPSHOT = "clinical_snapshot"
    DEMOGRAPHICS = "demographics"


class Principal:
    """An authenticated actor: identity + role + hospital/doctor context."""

    def __init__(self, user, db: Session):
        self.user = user
        self.role = user.role
        self.id = user.id
        self.db = db
        self.doctor: Doctor | None = None
        self.doctor_affiliations: list[DoctorHospitalAffiliation] = []
        self.staff_hospital_id: int | None = None
        self.admin_hospital_id: int | None = None
        self.chw: CommunityHealthWorker | None = None
        self._load_role_context()

    def _load_role_context(self):
        db = self.db
        if self.role == ROLE_DOCTOR:
            self.doctor = db.query(Doctor).filter(Doctor.user_id == self.user.id).first()
            if self.doctor:
                self.doctor_affiliations = db.query(DoctorHospitalAffiliation).filter(
                    DoctorHospitalAffiliation.doctor_id == self.doctor.id).all()
        elif self.role == ROLE_STAFF:
            staff = db.query(HospitalStaff).filter(HospitalStaff.user_id == self.user.id).first()
            self.staff_hospital_id = staff.hospital_id if staff else None
        elif self.role == ROLE_ADMIN:
            admin = db.query(HospitalAdmin).filter(HospitalAdmin.user_id == self.user.id).first()
            self.admin_hospital_id = admin.hospital_id if admin else None
        elif self.role == ROLE_CHW:
            self.chw = db.query(CommunityHealthWorker).filter(
                CommunityHealthWorker.user_id == self.user.id).first()

    # -------------------------------------------------- patient scope
    def own_patient(self) -> Patient | None:
        if self.role in (ROLE_USER, ROLE_CAREGIVER):
            return self.db.query(Patient).filter(Patient.user_id == self.user.id).first()
        return None

    def assigned_patient_ids(self) -> list[int]:
        """Patients this principal is authorized to see, by relationship/assignment."""
        db = self.db
        if self.role in (ROLE_USER, ROLE_CAREGIVER):
            p = self.own_patient()
            return [p.id] if p else []
        if self.role == ROLE_CHW and self.chw:
            return [a.patient_id for a in db.query(CommunityAssignment).filter(
                CommunityAssignment.chw_id == self.chw.id,
                CommunityAssignment.status == "ACTIVE").all()]
        if self.role == ROLE_DOCTOR and self.doctor:
            ids = {a.patient_id for a in db.query(Appointment).filter(
                Appointment.doctor_id == self.doctor.id).all()}
            return list(ids)
        return []

    # --------------------------------------- caregiver permission checks
    def caregiver_permissions(self, patient_id: int) -> set[str]:
        if self.role != ROLE_CAREGIVER:
            return set()
        rel = self.db.query(CaregiverRelationship).filter(
            CaregiverRelationship.caregiver_user_id == self.user.id,
            CaregiverRelationship.patient_id == patient_id,
            CaregiverRelationship.status == "ACTIVE").first()
        if not rel:
            return set()
        perms = self.db.query(CaregiverPermission).filter(
            CaregiverPermission.relationship_id == rel.id,
            CaregiverPermission.granted == True).all()  # noqa: E712
        return {p.permission for p in perms}

    # -------------------------------------------- break-glass emergency
    def active_break_glass(self, patient_id: int) -> EmergencyAccessEvent | None:
        ev = self.db.query(EmergencyAccessEvent).filter(
            EmergencyAccessEvent.actor_user_id == self.user.id,
            EmergencyAccessEvent.patient_id == patient_id,
            EmergencyAccessEvent.status.in_(["OPEN", "JUSTIFIED", "UNDER_REVIEW"]),
            EmergencyAccessEvent.expires_at > datetime.utcnow()).order_by(
            EmergencyAccessEvent.expires_at.desc()).first()
        return ev

    def invoke_break_glass(self, patient_id: int, reason: str) -> EmergencyAccessEvent:
        now = datetime.utcnow()
        ev = EmergencyAccessEvent(
            patient_id=patient_id, actor_user_id=self.user.id, reason=reason,
            requested_at=now,
            expires_at=now + timedelta(minutes=settings.BREAK_GLASS_MINUTES),
            justification_due=now + timedelta(hours=settings.BREAK_GLASS_JUSTIFICATION_HOURS),
            status="OPEN")
        self.db.add(ev)
        self.db.commit()
        self.db.refresh(ev)
        return ev

    # ------------------------------------------------- the core decision
    def can_access(self, patient_id: int, resource: str, context: dict | None = None) -> bool:
        """Identity + Role + Relationship + Permission + Clinical Context → decision.

        context may carry: purpose, speciality_key (clinical context), appointment_id.
        """
        context = context or {}
        db = self.db

        # 1) The patient themselves always has full access to their own record.
        if self.role in (ROLE_USER,):
            p = self.own_patient()
            return bool(p and p.id == patient_id)

        # 2) Caregiver: only via explicitly granted permissions (relationship alone grants nothing).
        if self.role == ROLE_CAREGIVER:
            perms = self.caregiver_permissions(patient_id)
            return resource in perms or bool(self.active_break_glass(patient_id))

        # 3) Doctor: scoped to own scheduled patients, filtered by clinical speciality context.
        if self.role == ROLE_DOCTOR:
            if patient_id not in self.assigned_patient_ids():
                return bool(self.active_break_glass(patient_id))
            speciality = context.get("speciality_key")
            if speciality and self.doctor and self.doctor.speciality_key != speciality:
                # Cross-speciality clinical record access is not automatic.
                return bool(self.active_break_glass(patient_id))
            return True

        # 4) Hospital staff: appointment/workflow info only — never clinical memory.
        if self.role == ROLE_STAFF:
            appt = db.query(Appointment).filter(
                Appointment.hospital_id == self.staff_hospital_id,
                Appointment.patient_id == patient_id).first()
            if appt and resource == Access.APPOINTMENTS:
                return True
            return bool(self.active_break_glass(patient_id))

        # 5) Hospital admin: administrative info for own hospital.
        if self.role == ROLE_ADMIN:
            appt = db.query(Appointment).filter(
                Appointment.hospital_id == self.admin_hospital_id,
                Appointment.patient_id == patient_id).first()
            return bool(appt)

        # 6) Community health worker: only assigned users, community-care scope.
        if self.role == ROLE_CHW:
            if patient_id in self.assigned_patient_ids():
                return resource in (Access.APPOINTMENTS, Access.DEMOGRAPHICS, Access.MEDICATIONS)
            return False

        return False

    def permitted_scope(self, patient_id: int, context: dict | None = None) -> dict:
        """The full set of resources this principal may read for a patient —
        used to pre-filter exactly what the AI service receives."""
        if self.role == ROLE_USER:
            p = self.own_patient()
            if p and p.id == patient_id:
                return {r: True for r in (Access.DEMOGRAPHICS, Access.CONDITIONS, Access.ALLERGIES,
                                          Access.MEDICATIONS, Access.PRESCRIPTIONS, Access.REPORTS,
                                          Access.HEALTH_LOGS, Access.SNAPSHOT, Access.APPOINTMENTS)}
            return {}
        if self.role == ROLE_CAREGIVER:
            perms = self.caregiver_permissions(patient_id)
            return {p_: True for p_ in perms}
        if self.role == ROLE_DOCTOR:
            if patient_id in self.assigned_patient_ids():
                return {r: True for r in (Access.DEMOGRAPHICS, Access.CONDITIONS, Access.ALLERGIES,
                                          Access.MEDICATIONS, Access.PRESCRIPTIONS, Access.REPORTS,
                                          Access.HEALTH_LOGS, Access.SNAPSHOT, Access.APPOINTMENTS)}
            return {}
        if self.role == ROLE_STAFF:
            appt = self.db.query(Appointment).filter(
                Appointment.hospital_id == self.staff_hospital_id,
                Appointment.patient_id == patient_id).first()
            return {Access.APPOINTMENTS: True, Access.DEMOGRAPHICS: True} if appt else {}
        if self.role == ROLE_CHW:
            if patient_id in self.assigned_patient_ids():
                return {Access.APPOINTMENTS: True, Access.DEMOGRAPHICS: True, Access.MEDICATIONS: True}
            return {}
        return {}
