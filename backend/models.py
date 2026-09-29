"""CareRoute AI — normalized data model.

Entities are structured so they map conceptually onto HL7 FHIR resources
(see fhir.py for the mapping layer): Patient, Practitioner, Organization,
Condition, Observation, Medication(Request), DiagnosticReport,
DocumentReference, Encounter, Appointment, CarePlan.
"""
from datetime import datetime, date

from sqlalchemy import (
    JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text,
)
from sqlalchemy.orm import relationship

from database import Base


def now():
    return datetime.utcnow()


# ---------------------------------------------------------------- identity
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    role = Column(String(32), index=True)  # USER | CAREGIVER | DOCTOR | STAFF | ADMIN | CHW
    name = Column(String(200), nullable=False)
    phone = Column(String(20), unique=True, index=True)          # user/caregiver login
    worker_id = Column(String(64), unique=True, index=True)      # doctor/staff/admin/chw login id
    password_hash = Column(String(300))
    mfa_enabled = Column(Boolean, default=True)
    device_unlock_enabled = Column(Boolean, default=False)
    active = Column(Boolean, default=True)
    onboarded = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


class UserProfile(Base):
    """FHIR: Patient (demographics captured at onboarding)."""
    __tablename__ = "user_profiles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    date_of_birth = Column(Date)
    blood_group = Column(String(8))          # voluntary
    preferred_language = Column(String(40), default="English")
    location_text = Column(String(250))
    latitude = Column(Float)
    longitude = Column(Float)
    accessibility_notes = Column(Text)
    relationship_to_care = Column(String(40))  # Myself / Spouse / Son / ... / Other
    relationship_other = Column(String(80))
    updated_at = Column(DateTime, default=now)


class Patient(Base):
    """FHIR: Patient. A person receiving care (may or may not hold a login)."""
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # set when self-managed
    display_name = Column(String(200), nullable=False)
    date_of_birth = Column(Date)
    blood_group = Column(String(8))
    preferred_language = Column(String(40), default="English")
    location_text = Column(String(250))
    latitude = Column(Float)
    longitude = Column(Float)
    emergency_contact_name = Column(String(120))
    emergency_contact_phone = Column(String(20))
    emergency_contact_relation = Column(String(40))
    created_at = Column(DateTime, default=now)

    conditions = relationship("MedicalCondition", backref="patient")
    allergies = relationship("Allergy", backref="patient")


# ------------------------------------------------------- caregiver access
class CaregiverRelationship(Base):
    __tablename__ = "caregiver_relationships"
    id = Column(Integer, primary_key=True)
    caregiver_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    relationship = Column(String(40))
    status = Column(String(20), default="PENDING")  # PENDING | ACTIVE | REVOKED
    created_at = Column(DateTime, default=now)


class CaregiverPermission(Base):
    __tablename__ = "caregiver_permissions"
    id = Column(Integer, primary_key=True)
    relationship_id = Column(Integer, ForeignKey("caregiver_relationships.id"), index=True)
    permission = Column(String(48))  # view_appointments, request_appointments, view_prescriptions,
                                     # view_medications, view_health_logs, assist_medication,
                                     # assist_navigation, emergency_assist, contact_emergency_person
    granted = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=now)


# ---------------------------------------------------------------- hospitals
class Hospital(Base):
    """FHIR: Organization. Static fields are publicly verified; ops fields are live."""
    __tablename__ = "hospitals"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    hospital_type = Column(String(40))       # Government | Private | Non-profit
    address = Column(String(300))
    city = Column(String(80))
    pincode = Column(String(12))
    latitude = Column(Float)
    longitude = Column(Float)
    phone = Column(String(24))
    emergency_phone = Column(String(24))
    website = Column(String(160))
    description = Column(Text)
    data_source = Column(String(40), default="VERIFIED_STATIC")  # VERIFIED_STATIC | PROTOTYPE
    verified_fields = Column(JSON)           # which fields are publicly verified
    created_at = Column(DateTime, default=now)

    departments = relationship("HospitalDepartment", backref="hospital")


class HospitalDepartment(Base):
    __tablename__ = "hospital_departments"
    id = Column(Integer, primary_key=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), index=True)
    name = Column(String(120))
    speciality_key = Column(String(48), index=True)  # orthopaedics, cardiology, oncology, ...
    description = Column(Text)


class HospitalFacility(Base):
    __tablename__ = "hospital_facilities"
    id = Column(Integer, primary_key=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), index=True)
    name = Column(String(120))
    category = Column(String(48))
    verified = Column(Boolean, default=False)


class Doctor(Base):
    """FHIR: Practitioner. Controlled demonstration identities — no real-person credentials."""
    __tablename__ = "doctors"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    name = Column(String(160), nullable=False)
    qualification = Column(String(160))
    speciality_key = Column(String(48), index=True)
    designation = Column(String(120))
    years_experience = Column(Integer)
    verification_status = Column(String(40), default="DEMO_VERIFIED")  # demo identity
    profile_note = Column(Text)


class DoctorHospitalAffiliation(Base):
    __tablename__ = "doctor_hospital_affiliations"
    id = Column(Integer, primary_key=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), index=True)
    department_id = Column(Integer, ForeignKey("hospital_departments.id"))
    opd_days = Column(String(80))
    consultation_hours = Column(String(80))


class HospitalStaff(Base):
    __tablename__ = "hospital_staff"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), index=True)
    designation = Column(String(80))
    department = Column(String(120))


class HospitalAdmin(Base):
    __tablename__ = "hospital_admins"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), index=True)


class CommunityHealthWorker(Base):
    __tablename__ = "community_health_workers"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    worker_id = Column(String(64))
    organization = Column(String(200))
    region = Column(String(120))


class CommunityAssignment(Base):
    __tablename__ = "community_assignments"
    id = Column(Integer, primary_key=True)
    chw_id = Column(Integer, ForeignKey("community_health_workers.id"), index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    priority = Column(String(20), default="ROUTINE")  # ROUTINE | WELLNESS_DUE | ESCALATED
    status = Column(String(20), default="ACTIVE")
    assigned_at = Column(DateTime, default=now)


# ------------------------------------------------------------ health memory
class MedicalCondition(Base):
    """FHIR: Condition."""
    __tablename__ = "medical_conditions"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    condition = Column(String(200))
    speciality_key = Column(String(48), index=True)
    diagnosed_on = Column(Date)
    status = Column(String(24), default="ACTIVE")  # ACTIVE | MANAGED | RESOLVED
    notes = Column(Text)
    source = Column(String(40), default="USER_REPORTED")  # USER_REPORTED | PROTOTYPE_CLINICAL


class Allergy(Base):
    __tablename__ = "allergies"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    allergen = Column(String(120))
    severity = Column(String(24))   # MILD | MODERATE | SEVERE
    reaction = Column(String(200))


class Medication(Base):
    """FHIR: Medication + MedicationRequest (statement side)."""
    __tablename__ = "medications"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    name = Column(String(160))
    dosage = Column(String(80))
    frequency = Column(String(80))
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(24), default="ACTIVE")  # ACTIVE | COMPLETED | PAUSED
    prescribed_by = Column(String(160))
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=True)
    last_taken_on = Column(Date, nullable=True)  # set by the patient's "taken today" action
    notes = Column(Text)


class Prescription(Base):
    """FHIR: MedicationRequest. Always tied to patient + doctor + hospital."""
    __tablename__ = "prescriptions"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    issued_at = Column(DateTime, default=now)
    diagnosis_text = Column(String(300))
    instructions = Column(Text)
    follow_up_on = Column(Date)
    items = relationship("PrescriptionItem", backref="prescription", cascade="all,delete")


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"
    id = Column(Integer, primary_key=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), index=True)
    medicine = Column(String(160))
    dosage = Column(String(80))
    frequency = Column(String(80))
    duration_days = Column(Integer)
    instructions = Column(Text)


class MedicalReport(Base):
    """FHIR: DiagnosticReport + DocumentReference (secure, access-controlled)."""
    __tablename__ = "medical_reports"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    title = Column(String(200))
    report_type = Column(String(48))         # LAB | IMAGING | DOCUMENT
    speciality_key = Column(String(48), index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"))
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=True)
    report_date = Column(Date)
    summary = Column(Text)
    findings = Column(Text)
    file_name = Column(String(200))
    content_type = Column(String(80))
    file_data = Column(LargeBinary)          # synthetic demo document
    data_source = Column(String(40), default="PROTOTYPE_UPLOAD")


class HealthLog(Base):
    """FHIR: Observation (patient-reported daily entry)."""
    __tablename__ = "health_logs"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    logged_at = Column(DateTime, default=now)
    pain_level = Column(Integer)             # 0-10
    temperature_c = Column(Float)
    mood = Column(String(40))
    symptoms = Column(Text)
    adherence = Column(String(24))           # TAKEN_ALL | PARTIAL | MISSED
    notes = Column(Text)


class ClinicalSnapshotCache(Base):
    __tablename__ = "clinical_snapshots"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    speciality_key = Column(String(48))
    viewer_role = Column(String(32))
    generated_at = Column(DateTime, default=now)
    content = Column(JSON)


# ------------------------------------------------------------- appointments
class Appointment(Base):
    """FHIR: Appointment. State machine: REQUESTED → CONFIRMED/REJECTED/RESCHEDULED → COMPLETED."""
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), index=True)
    department_id = Column(Integer, ForeignKey("hospital_departments.id"))
    requested_by_user_id = Column(Integer, ForeignKey("users.id"))
    requested_on_behalf = Column(String(40))  # SELF | CAREGIVER | CHW
    appointment_date = Column(Date)
    time_slot = Column(String(40))
    status = Column(String(24), default="REQUESTED", index=True)
    reason = Column(Text)
    staff_note = Column(Text)
    rescheduled_from_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    token_number = Column(String(16))
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now)


# ---------------------------------------------------------------- emergency
class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    name = Column(String(120))
    phone = Column(String(20))
    relationship = Column(String(40))
    is_primary = Column(Boolean, default=False)


class EmergencyEvent(Base):
    __tablename__ = "emergency_events"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    triggered_by_user_id = Column(Integer, ForeignKey("users.id"))
    triggered_at = Column(DateTime, default=now)
    latitude = Column(Float)
    longitude = Column(Float)
    location_text = Column(String(250))
    situation = Column(Text)
    status = Column(String(24), default="ACTIVE")   # ACTIVE | RESOLVED
    summary = Column(JSON)                           # Emergency Health Summary (authorized only)
    voice_script = Column(Text)
    facility_hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)


class EmergencyAccessEvent(Base):
    """Break-glass access. Time-boxed, audited, requires post-event justification."""
    __tablename__ = "emergency_access_events"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    reason = Column(Text)
    requested_at = Column(DateTime, default=now)
    expires_at = Column(DateTime)
    justification = Column(Text)
    justification_due = Column(DateTime)
    status = Column(String(24), default="OPEN")     # OPEN | JUSTIFIED | UNDER_REVIEW


# ------------------------------------------------------------ community care
class CommunityVisit(Base):
    __tablename__ = "community_visits"
    id = Column(Integer, primary_key=True)
    chw_id = Column(Integer, ForeignKey("community_health_workers.id"), index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    visit_date = Column(Date)
    wellness_status = Column(String(40))   # WELL | NEEDS_ATTENTION | UNREACHABLE
    observations = Column(Text)
    escalation_flag = Column(Boolean, default=False)
    follow_up_on = Column(Date)


class MedicalCamp(Base):
    __tablename__ = "medical_camps"
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    camp_date = Column(Date)
    location_text = Column(String(250))
    latitude = Column(Float)
    longitude = Column(Float)
    speciality = Column(String(80))
    services = Column(Text)
    organizer = Column(String(200))
    registration = Column(String(200))
    contact = Column(String(60))
    verified_source = Column(String(200))  # provenance; demo camps are clearly labeled


# ----------------------------------------------------- platform / security
class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    type = Column(String(48))
    title = Column(String(200))
    body = Column(Text)
    related_id = Column(Integer)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)
    # Cross-dashboard live-sync cursor: bumped on every new notification for the
    # recipient so /sync clients can detect new activity cheaply.
    sync_token = Column(String(64), index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    actor_role = Column(String(32))
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    hospital_id = Column(Integer, nullable=True)
    action = Column(String(64), index=True)
    record_ref = Column(String(120))
    purpose = Column(String(160))
    result = Column(String(16))            # ALLOWED | DENIED
    detail = Column(Text)
    ip = Column(String(64))
    device = Column(String(120))
    created_at = Column(DateTime, default=now, index=True)


class DataSource(Base):
    __tablename__ = "data_sources"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))
    provider_type = Column(String(60))     # PROTOTYPE | AUTHORIZED_HOSPITAL_API | ...
    status = Column(String(40))            # CONNECTED | UNAVAILABLE | PLANNED
    scope = Column(String(200))
    last_synced_at = Column(DateTime, nullable=True)
    config = Column(JSON)


class OtpCode(Base):
    __tablename__ = "otp_codes"
    id = Column(Integer, primary_key=True)
    identifier = Column(String(80), index=True)   # phone or worker id
    code = Column(String(8))
    purpose = Column(String(40))
    expires_at = Column(DateTime)
    used = Column(Boolean, default=False)


class DeviceCredential(Base):
    """Simulated passkey: a device-bound secret is enrolled; the raw secret never
    leaves the device. No biometric images are ever stored."""
    __tablename__ = "device_credentials"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    device_name = Column(String(120))
    secret_hash = Column(String(300))
    created_at = Column(DateTime, default=now)
    last_used = Column(DateTime, nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    token_hash = Column(String(300))
    expires_at = Column(DateTime)
    revoked = Column(Boolean, default=False)
