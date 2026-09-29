"""CareRoute AI — audit logging. Every sensitive access decision lands here."""
from sqlalchemy.orm import Session

from models import AuditLog

# Canonical auditable actions.
ACTIONS = [
    "LOGIN", "LOGOUT", "DEVICE_ENROLL", "ONBOARDING_COMPLETE",
    "VIEW_CLINICAL_SNAPSHOT", "VIEW_PRESCRIPTION", "VIEW_REPORT", "VIEW_HEALTH_LOG",
    "VIEW_MEDICATIONS", "VIEW_APPOINTMENTS", "APPOINTMENT_REQUEST", "APPOINTMENT_CONFIRM",
    "APPOINTMENT_REJECT", "APPOINTMENT_RESCHEDULE", "PRESCRIPTION_CREATED", "CONSULTATION_NOTE",
    "PERMISSION_GRANTED", "PERMISSION_MODIFIED", "PERMISSION_REVOKED",
    "EMERGENCY_TRIGGERED", "EMERGENCY_RESOLVED", "EMERGENCY_ACCESS",
    "ACCESS_DENIED", "AI_SUMMARY_REQUESTED", "BREAK_GLASS_JUSTIFY", "CHW_VISIT_RECORDED",
    "CAMP_VIEWED",
]


def audit(db: Session, actor, action: str, patient_id: int | None = None,
          hospital_id: int | None = None, record_ref: str | None = None,
          purpose: str | None = None, result: str = "ALLOWED", detail: str | None = None,
          ip: str | None = None, device: str | None = None,
          actor_user_id: int | None = None, actor_role: str | None = None) -> AuditLog:
    """actor may be a Principal or None (system/pre-auth events); explicit
    actor_user_id/actor_role overrides cover events logged before a Principal exists."""
    entry = AuditLog(
        actor_user_id=actor_user_id if actor_user_id is not None else (getattr(actor, "id", None) if actor else None),
        actor_role=actor_role if actor_role is not None else (getattr(actor, "role", None) if actor else "SYSTEM"),
        patient_id=patient_id, hospital_id=hospital_id, action=action,
        record_ref=record_ref, purpose=purpose, result=result, detail=detail,
        ip=ip, device=device,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
