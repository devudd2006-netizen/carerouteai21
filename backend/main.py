"""CareRoute AI — FastAPI application: all API routes, every one authorization-checked."""
import json
import math
from datetime import date, datetime, timedelta

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import ai_service
from audit import audit
from authz import (Access, CAREGIVER_PERMISSIONS, ROLE_ADMIN, ROLE_CAREGIVER, ROLE_CHW,
                   ROLE_DOCTOR, ROLE_STAFF, ROLE_USER, Principal)
from config import settings
from database import get_db
from deps import get_current_principal, get_request_meta, rate_limit, require_roles
from fhir import SPECIALITIES, suggest_speciality
from models import (
    Allergy, Appointment, AuditLog, CaregiverPermission, CaregiverRelationship,
    CommunityAssignment, CommunityHealthWorker, CommunityVisit, DataSource, DeviceCredential,
    Doctor, DoctorHospitalAffiliation, EmergencyAccessEvent, EmergencyContact, EmergencyEvent,
    HealthLog, Hospital, HospitalDepartment, HospitalFacility, HospitalStaff, MedicalCamp,
    MedicalCondition, MedicalReport, Medication, Notification, OtpCode, Patient,
    Prescription, PrescriptionItem, RefreshToken, UserProfile, User,
)
from providers import (GooglePlacesProvider, OverpassProvider, PlacesUnavailableError,
                       PrototypeHospitalProvider, get_provider)
from security import (constant_time_eq, create_access_token, create_refresh_token,
                      generate_otp, hash_password, hash_token, otp_expiry)

app = FastAPI(title="CareRoute AI", version="1.0.0",
              description="Multi-hospital healthcare coordination platform (prototype)")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ helpers
def haversine_km(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 1)


def patient_for_check(db: Session, patient_id: int) -> Patient:
    p = db.get(Patient, patient_id)
    if not p:
        raise HTTPException(404, "Record not found")
    return p


def deny(principal: Principal, patient_id: int, resource: str, meta: dict, purpose: str):
    audit(principal.db, principal, "ACCESS_DENIED", patient_id=patient_id,
          record_ref=resource, purpose=purpose, result="DENIED",
          ip=meta.get("ip"), device=meta.get("device"))
    raise HTTPException(403, "You do not have permission to access this information")


def notify(db: Session, user_id: int, type_: str, title: str, body: str, related_id=None):
    """Create a notification and bump the user's cross-dashboard sync token.

    Every dashboards-watching /sync client (this user's other browser sessions —
    e.g. the four-laptop demo) sees the token change within ~3s and refreshes live.
    """
    token = f"{user_id}:{int(datetime.utcnow().timestamp() * 1000)}"
    db.add(Notification(user_id=user_id, type=type_, title=title, body=body,
                        related_id=related_id, sync_token=token))
    db.commit()


def appointment_out(a: Appointment, db: Session) -> dict:
    doc = db.get(Doctor, a.doctor_id)
    hosp = db.get(Hospital, a.hospital_id)
    pat = db.get(Patient, a.patient_id)
    dept = db.get(HospitalDepartment, a.department_id) if a.department_id else None
    return {
        "id": a.id, "patient_id": a.patient_id, "patient_name": pat.display_name if pat else None,
        "doctor_id": a.doctor_id, "doctor_name": doc.name if doc else None,
        "speciality_key": doc.speciality_key if doc else None,
        "hospital_id": a.hospital_id, "hospital_name": hosp.name if hosp else None,
        "department": dept.name if dept else None,
        "appointment_date": str(a.appointment_date), "time_slot": a.time_slot,
        "status": a.status, "reason": a.reason, "staff_note": a.staff_note,
        "token_number": a.token_number, "requested_on_behalf": a.requested_on_behalf,
        "created_at": str(a.created_at), "updated_at": str(a.updated_at),
    }


# =================================================================== AUTH
class OtpRequest(BaseModel):
    identifier: str  # phone (+91...) or worker id (DOC101/STF201/ADM001/CHW042)


class OtpVerify(BaseModel):
    identifier: str
    code: str
    device_name: str | None = None


@app.post("/auth/request-otp", tags=["auth"])
def request_otp(body: OtpRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(request)
    identifier = body.identifier.strip()
    user = db.query(User).filter(
        (User.phone == identifier) | (User.worker_id == identifier)).first()
    # For unknown phone numbers we still create an OTP — account is created at verify
    # only for phone (user/caregiver) identifiers; worker ids must exist.
    if not user and not identifier.startswith("+"):
        raise HTTPException(404, "No account found for this ID. Use your phone number to create an account.")
    code = generate_otp()
    db.add(OtpCode(identifier=identifier, code=code, purpose="LOGIN", expires_at=otp_expiry()))
    db.commit()
    # Prototype: the OTP is returned for the demo (no SMS gateway connected).
    # Production: send via SMS gateway; never return the code.
    return {"sent": True, "channel": "prototype_display",
            "demo_otp": code,
            "message": "Prototype mode: OTP shown here instead of SMS. Production sends via SMS gateway."}


@app.post("/auth/verify-otp", tags=["auth"])
def verify_otp(body: OtpVerify, request: Request, db: Session = Depends(get_db)):
    rate_limit(request)
    identifier = body.identifier.strip()
    row = db.query(OtpCode).filter(OtpCode.identifier == identifier, OtpCode.used == False,  # noqa: E712
                                   OtpCode.expires_at > datetime.utcnow()).order_by(
        OtpCode.id.desc()).first()
    if not row or not constant_time_eq(row.code, body.code.strip()):
        audit(db, None, "LOGIN", result="DENIED", detail=f"invalid OTP for {identifier[:4]}***",
              ip=request.client.host if request.client else None,
              device=(request.headers.get("user-agent") or "")[:120])
        raise HTTPException(401, "Invalid or expired code")
    row.used = True
    user = db.query(User).filter(
        (User.phone == identifier) | (User.worker_id == identifier)).first()
    if not user:
        if not identifier.startswith("+"):
            raise HTTPException(404, "No account found for this ID")
        user = User(role=ROLE_USER, name="New CareRoute User", phone=identifier)
        db.add(user)
        db.commit()
        db.refresh(user)
    if not user.active:
        raise HTTPException(403, "Account deactivated. Contact support.")
    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=hash_token(refresh),
                        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)))
    db.commit()
    audit(db, None, "LOGIN", actor_user_id=user.id, actor_role=user.role, result="ALLOWED",
          ip=request.client.host if request.client else None,
          device=(request.headers.get("user-agent") or "")[:120])
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer",
            "user": {"id": user.id, "role": user.role, "name": user.name,
                     "phone": user.phone, "worker_id": user.worker_id,
                     "mfa_enabled": user.mfa_enabled, "onboarded": user.onboarded}}


class RefreshBody(BaseModel):
    refresh_token: str


@app.post("/auth/refresh", tags=["auth"])
def refresh(body: RefreshBody, db: Session = Depends(get_db)):
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(body.refresh_token),
                                        RefreshToken.revoked == False,  # noqa: E712
                                        RefreshToken.expires_at > datetime.utcnow()).first()
    if not row:
        raise HTTPException(401, "Session expired. Please sign in again.")
    user = db.get(User, row.user_id)
    return {"access_token": create_access_token(user.id, user.role), "token_type": "bearer"}


@app.post("/auth/logout", tags=["auth"])
def logout(body: RefreshBody, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(body.refresh_token)).first()
    if row:
        row.revoked = True
        db.commit()
    audit(db, principal, "LOGOUT")
    return {"logged_out": True}


class DeviceEnroll(BaseModel):
    device_name: str


@app.post("/auth/device/enroll", tags=["auth"])
def device_enroll(body: DeviceEnroll, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    """Passkey-style device unlock. A device-bound secret is generated and shown ONCE;
    only its hash is stored. No biometric images are ever stored."""
    secret = __import__("secrets").token_urlsafe(32)
    db.add(DeviceCredential(user_id=principal.id, device_name=body.device_name[:120],
                            secret_hash=hash_password(f"{principal.id}:{body.device_name}:{secret}")))
    principal.user.device_unlock_enabled = True
    db.commit()
    audit(db, principal, "DEVICE_ENROLL", detail=body.device_name)
    return {"enrolled": True, "device_secret": secret,
            "note": "Store this device secret securely — it is shown only once. "
                    "The server stores only a hash; no biometric data is collected."}


class DeviceUnlock(BaseModel):
    identifier: str
    device_name: str
    device_secret: str


@app.post("/auth/device/unlock", tags=["auth"])
def device_unlock(body: DeviceUnlock, request: Request, db: Session = Depends(get_db)):
    rate_limit(request)
    user = db.query(User).filter(
        (User.phone == body.identifier) | (User.worker_id == body.identifier)).first()
    if not user or not user.device_unlock_enabled:
        raise HTTPException(401, "Device unlock not available for this account")
    from security import verify_password
    ok = False
    for c in db.query(DeviceCredential).filter(DeviceCredential.user_id == user.id,
                                               DeviceCredential.device_name == body.device_name).all():
        if verify_password(f"{user.id}:{body.device_name}:{body.device_secret}", c.secret_hash):
            ok = True
            c.last_used = datetime.utcnow()
            break
    if not ok:
        raise HTTPException(401, "Device verification failed")
    access = create_access_token(user.id, user.role)
    audit(db, None, "LOGIN", actor_user_id=user.id, actor_role=user.role,
          detail="device unlock", ip=request.client.host if request.client else None)
    return {"access_token": access, "token_type": "bearer",
            "user": {"id": user.id, "role": user.role, "name": user.name, "onboarded": user.onboarded}}


@app.get("/auth/me", tags=["auth"])
def me(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    u = principal.user
    own = principal.own_patient() if principal.role in (ROLE_USER, ROLE_CAREGIVER) else None
    cared_patient_id = own.id if own else None
    if principal.role == ROLE_CAREGIVER and cared_patient_id is None:
        rel = db.query(CaregiverRelationship).filter(
            CaregiverRelationship.caregiver_user_id == u.id,
            CaregiverRelationship.status == "ACTIVE").first()
        cared_patient_id = rel.patient_id if rel else None
    return {"id": u.id, "role": u.role, "name": u.name, "phone": u.phone,
            "worker_id": u.worker_id, "onboarded": u.onboarded,
            "mfa_enabled": u.mfa_enabled, "device_unlock_enabled": u.device_unlock_enabled,
            "patient_id": cared_patient_id if principal.role == ROLE_CAREGIVER else (own.id if own else None),
            "doctor": {"id": principal.doctor.id, "name": principal.doctor.name,
                       "speciality_key": principal.doctor.speciality_key,
                       "qualification": principal.doctor.qualification,
                       "designation": principal.doctor.designation,
                       "hospital_ids": [a.hospital_id for a in principal.doctor_affiliations]}
                      if principal.doctor else None,
            "staff_hospital_id": principal.staff_hospital_id,
            "admin_hospital_id": principal.admin_hospital_id,
            "chw_id": principal.chw.id if principal.chw else None}


# =============================================================== ONBOARDING
class OnboardingAllergy(BaseModel):
    allergen: str
    severity: str = "MODERATE"
    reaction: str | None = None


class OnboardingMedication(BaseModel):
    name: str
    dosage: str | None = None
    frequency: str | None = None


class OnboardingBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    date_of_birth: date | None = None
    blood_group: str | None = None
    preferred_language: str = "English"
    location_text: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    accessibility_notes: str | None = None
    relationship_to_care: str = "Myself"
    relationship_other: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    emergency_contact_relation: str | None = None
    allergies: list[OnboardingAllergy] = []
    conditions: list[str] = []
    medications: list[OnboardingMedication] = []
    important_history: str | None = None


@app.post("/users/onboard", tags=["users"])
def onboard(body: OnboardingBody, principal: Principal = Depends(get_current_principal),
            db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    if principal.role != ROLE_USER:
        raise HTTPException(403, "Onboarding is for CareRoute user accounts")
    if db.query(Patient).filter(Patient.user_id == principal.id).first():
        raise HTTPException(409, "This account is already onboarded")
    p = Patient(user_id=principal.id, display_name=body.name, date_of_birth=body.date_of_birth,
                blood_group=(body.blood_group or None), preferred_language=body.preferred_language,
                location_text=body.location_text, latitude=body.latitude, longitude=body.longitude,
                emergency_contact_name=body.emergency_contact_name,
                emergency_contact_phone=body.emergency_contact_phone,
                emergency_contact_relation=body.emergency_contact_relation)
    db.add(p)
    db.flush()
    db.add(UserProfile(user_id=principal.id, date_of_birth=body.date_of_birth,
                       blood_group=body.blood_group or None,
                       preferred_language=body.preferred_language, location_text=body.location_text,
                       latitude=body.latitude, longitude=body.longitude,
                       accessibility_notes=body.accessibility_notes,
                       relationship_to_care=body.relationship_to_care,
                       relationship_other=body.relationship_other))
    for cond in body.conditions:
        c = cond.strip()
        if c:
            db.add(MedicalCondition(patient_id=p.id, condition=c,
                                    speciality_key=_guess_speciality(c), status="ACTIVE",
                                    source="USER_REPORTED", notes=body.important_history))
    for a in body.allergies:
        db.add(Allergy(patient_id=p.id, allergen=a.allergen[:120], severity=a.severity,
                       reaction=a.reaction))
    for m in body.medications:
        if m.name.strip():
            db.add(Medication(patient_id=p.id, name=m.name.strip()[:160], dosage=m.dosage,
                              frequency=m.frequency, status="ACTIVE",
                              start_date=date.today(), prescribed_by="Self-reported at onboarding"))
    if body.emergency_contact_name and body.emergency_contact_phone:
        db.add(EmergencyContact(patient_id=p.id, name=body.emergency_contact_name,
                                phone=body.emergency_contact_phone,
                                relationship=body.emergency_contact_relation or "Family",
                                is_primary=True))
    principal.user.onboarded = True
    db.commit()
    audit(db, principal, "ONBOARDING_COMPLETE", patient_id=p.id, ip=meta.get("ip"))
    return {"onboarded": True, "patient_id": p.id}


def _guess_speciality(text: str) -> str:
    sugg = suggest_speciality(text)
    return sugg[0]["speciality_key"] if sugg else "general_medicine"


@app.get("/users/me/profile", tags=["users"])
def my_profile(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    prof = db.query(UserProfile).filter(UserProfile.user_id == principal.id).first()
    return {"user": {"name": principal.user.name, "phone": principal.user.phone,
                     "role": principal.user.role},
            "profile": {"date_of_birth": str(prof.date_of_birth) if prof and prof.date_of_birth else None,
                        "blood_group": prof.blood_group if prof else None,
                        "preferred_language": prof.preferred_language if prof else "English",
                        "location_text": prof.location_text if prof else None,
                        "accessibility_notes": prof.accessibility_notes if prof else None,
                        "relationship_to_care": prof.relationship_to_care if prof else None}}


# ================================================================ HOSPITALS
@app.get("/hospitals", tags=["hospitals"])
def list_hospitals(speciality: str | None = None, emergency: bool = False, lat: float | None = None,
                   lng: float | None = None, db: Session = Depends(get_db)):
    provider = get_provider(db)
    try:
        hospitals = provider.list_hospitals(db)
    except PlacesUnavailableError as exc:
        # Never silently replace a live location search with a fixed demo city.
        return {"hospitals": [],
                "provider": provider.integration_status(),
                "provider_failed": True,
                "needs_location": lat is None or lng is None,
                "fallback_note": str(exc) or "Live discovery unavailable — no static hospital fallback is used."}
    return {"hospitals": _finish_hospital_list(hospitals, speciality, emergency, lat, lng, db),
            "provider": provider.integration_status()}


def _finish_hospital_list(hospitals, speciality, emergency, lat, lng, db):
    if speciality:
        hospitals = [h for h in hospitals
                     if any(d["speciality_key"] == speciality for d in h["departments"])]
    if emergency:
        result = []
        for h in hospitals:
            has_em = db.query(HospitalFacility).filter(
                HospitalFacility.hospital_id == h["id"],
                HospitalFacility.category == "emergency").first() or h.get("emergency_phone")
            if has_em:
                result.append(h)
        hospitals = result
    for h in hospitals:
        h["distance_km"] = haversine_km(lat, lng, h["latitude"], h["longitude"])
    if lat is not None:
        hospitals.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 1e9)
    return hospitals


# -------------------------------------------------- DYNAMIC DISCOVERY (§2/§32)
# LOCATION → HEALTHCARE NEED → SUITABLE FACILITIES → DISTANCE/RELEVANCE.
# With GOOGLE_MAPS_API_KEY set, results are live Google Places data for ANY
# location; without it, the verified prototype directory is searched the same
# way so the workflow (and location-change behaviour) is fully demonstrable.
@app.get("/hospitals/discover", tags=["hospitals"])
def discover_hospitals(lat: float | None = None, lng: float | None = None,
                       location_text: str | None = None, query: str | None = None,
                       speciality: str | None = None, emergency: bool = False,
                       multi_specialty: bool = False, highly_rated: bool = False,
                       radius_km: float = 25.0, db: Session = Depends(get_db)):
    settings_local = get_provider(db)
    fallback_note = None
    provider_failed = False
    rows: list[dict]
    data_source: str

    if isinstance(settings_local, GooglePlacesProvider):
        places = None
        if query:
            places = settings_local._search_text(query, lat, lng)
        elif lat is not None and lng is not None:
            places = settings_local._search_nearby(lat, lng)
        if places is None:
            provider_failed = True   # §7: honest failure — no demo fallback
            rows, data_source = [], "GOOGLE_PLACES"
        else:
            rows = [GooglePlacesProvider._place_to_hospital(p) for p in places]
            data_source = "GOOGLE_PLACES_LIVE"
    elif isinstance(settings_local, OverpassProvider):
        if lat is None or lng is None:
            # No coordinates → no live search. We do NOT silently search demo data.
            return {"facilities": [], "in_radius": [], "nearest_outside_km": None,
                    "next_radius_km": next((r for r in (5, 10, 25, 100) if r > radius_km), None),
                    "data_source": "OPENSTREETMAP_OVERPASS",
                    "provider": settings_local.integration_status(),
                    "needs_location": True,
                    "search": {"lat": lat, "lng": lng, "location_text": location_text,
                               "query": query, "speciality": speciality, "emergency": emergency,
                               "multi_specialty": multi_specialty, "highly_rated": highly_rated,
                               "radius_km": radius_km},
                    "disclaimer": "Set your location to search real nearby healthcare facilities."}
        out = settings_local.search_nearby_hospitals(
            lat, lng, int(radius_km * 1000),
            filters={"emergency": emergency, "query": query, "speciality": speciality,
                     "limit": 40 if not query else 60})
        print(f"[discover] provider=Overpass status={out['status']} count={out['count']} "
              f"lat={lat} lng={lng} radius_km={radius_km}")
        if out["status"] == "failed":
            provider_failed = True   # §7: honest technical failure state
            rows, data_source = [], "OPENSTREETMAP_OVERPASS"
        else:
            rows = out["results"]
            data_source = "OPENSTREETMAP_OVERPASS"
            # Free-text filter on genuinely mapped facility type when a query
            # accompanies a live search. Department/speciality data is unavailable
            # in OSM, so filters that would require it are honestly not applied.
            if query:
                text = query.lower()
                SYNONYMS = {"hospital": {"Hospital"}, "clinic": {"Clinic"},
                            "doctor": {"Doctor"}, "emergency": {"Hospital"}}
                wanted = set()
                for t in text.split():
                    wanted |= SYNONYMS.get(t, set())
                if wanted:
                    rows = [r for r in rows if r["hospital_type"] in wanted]
    elif isinstance(settings_local, PrototypeHospitalProvider):
        # Explicit demo directory (development/demo use ONLY via CAREROUTE_PROVIDER=prototype).
        rows = settings_local.list_hospitals(db)
        data_source = "PROTOTYPE_DIRECTORY"
        text = (query or "").lower()
        NEED_SYNONYMS = {
            "eye": {"ophthalmology"}, "vision": {"ophthalmology"},
            "bone": {"orthopaedics"}, "joint": {"orthopaedics"}, "knee": {"orthopaedics"},
            "ortho": {"orthopaedics"}, "orthopedic": {"orthopaedics"},
            "heart": {"cardiology"}, "cardiac": {"cardiology"}, "chest": {"cardiology"},
            "skin": {"dermatology"}, "cancer": {"oncology"}, "tumor": {"oncology"},
            "kidney": {"urology"}, "urinary": {"urology"},
            "ear": {"ent"}, "throat": {"ent"},
            "women": {"obstetrics_gynaecology"}, "maternity": {"obstetrics_gynaecology"},
            "fever": {"general_medicine"}, "emergency": {"emergency"}, "trauma": {"emergency"},
        }

        def _term_matches(term: str, hay: str, spec_keys: set) -> bool:
            if term in hay:
                return True
            keys = NEED_SYNONYMS.get(term)
            return bool(keys and keys & spec_keys)

        if text:
            def _matches(h: dict) -> bool:
                hay = " ".join([h.get("name", ""), h.get("address", ""), h.get("city", ""),
                                 h.get("description", ""), h.get("hospital_type", ""),
                                 " ".join(d["name"] + " " + (d.get("speciality_key") or "")
                                          for d in h["departments"])]).lower()
                spec_keys = {d.get("speciality_key") for d in h["departments"]
                             if d.get("speciality_key")}
                return all(_term_matches(t, hay, spec_keys) for t in text.split())
            rows = [h for h in rows if _matches(h)]
    else:
        # Any other provider (authorized integrations): try its directory search.
        rows = settings_local.list_hospitals(db)
        data_source = settings_local.name
        text = (query or "").lower()
        # Lay need-terms → speciality keys (§2: "eye emergency" → eye-care facilities).
        NEED_SYNONYMS = {
            "eye": {"ophthalmology"}, "vision": {"ophthalmology"},
            "bone": {"orthopaedics"}, "joint": {"orthopaedics"}, "knee": {"orthopaedics"},
            "ortho": {"orthopaedics"}, "orthopedic": {"orthopaedics"},
            "heart": {"cardiology"}, "cardiac": {"cardiology"}, "chest": {"cardiology"},
            "skin": {"dermatology"}, "cancer": {"oncology"}, "tumor": {"oncology"},
            "kidney": {"urology"}, "urinary": {"urology"},
            "ear": {"ent"}, "throat": {"ent"},
            "women": {"obstetrics_gynaecology"}, "maternity": {"obstetrics_gynaecology"},
            "fever": {"general_medicine"}, "emergency": {"emergency"}, "trauma": {"emergency"},
        }

        def _term_matches(term: str, hay: str, spec_keys: set) -> bool:
            if term in hay:
                return True
            keys = NEED_SYNONYMS.get(term)
            return bool(keys and keys & spec_keys)

        if text:
            def _matches(h: dict) -> bool:
                hay = " ".join([h.get("name", ""), h.get("address", ""), h.get("city", ""),
                                 h.get("description", ""), h.get("hospital_type", ""),
                                 " ".join(d["name"] + " " + (d.get("speciality_key") or "")
                                          for d in h["departments"])]).lower()
                spec_keys = {d.get("speciality_key") for d in h["departments"]
                             if d.get("speciality_key")}
                return all(_term_matches(t, hay, spec_keys) for t in text.split())
            rows = [h for h in rows if _matches(h)]

    # Speciality/facility filters — only for directory rows that genuinely carry
    # department data. Live OSM/Places results are already scoped by the provider
    # query; filters needing unavailable data are honestly not applied.
    if speciality and data_source == "PROTOTYPE_DIRECTORY":
        rows = [h for h in rows
                if any(d["speciality_key"] == speciality for d in h["departments"])]
    if emergency and data_source == "PROTOTYPE_DIRECTORY":
        rows = [h for h in rows if h.get("emergency_phone")
                or db.query(HospitalFacility).filter(
                    HospitalFacility.hospital_id == h["id"],
                    HospitalFacility.category == "emergency").first()]
    if multi_specialty and data_source == "PROTOTYPE_DIRECTORY":
        rows = [h for h in rows if len(h["departments"]) >= 4]
    if highly_rated and data_source == "PROTOTYPE_DIRECTORY":
        # Only keeps facilities with genuine public rating data (Places mode);
        # in the prototype directory nothing claims an invented rating.
        rows = [h for h in rows if h.get("public_rating")]

    # WHY surfaced (§3): factual, per-facility chips instead of "best hospital" claims.
    for h in rows:
        h["distance_km"] = haversine_km(lat, lng, h["latitude"], h["longitude"])
        why: list[str] = []
        if h.get("distance_km") is not None:
            why.append(f"{h['distance_km']} km away")
        if speciality and any(d["speciality_key"] == speciality for d in h["departments"]):
            why.append("matches requested speciality")
        if len(h["departments"]) >= 4:
            why.append("multi-specialty facility")
        if h.get("emergency_phone"):
            why.append("emergency-capable")
        if h.get("public_rating"):
            why.append(f"highly rated by patients ({h['public_rating']}★)")
        h["why"] = why[:3]

    # Transparent ranking (§31): distance first when known; emergency capability and
    # public rating are shown as factors — never a fabricated "best hospital" score.
    def _rank(h: dict):
        d = h.get("distance_km")
        return (1e9 if d is None else d,
                0 if (emergency and h.get("emergency_phone")) else 1,
                -(h.get("public_rating") or 0))
    rows.sort(key=_rank)

    # Radius semantics (§6/§17): strict inside-radius list first, plus honest
    # expansion hints computed from the nearest facility beyond the radius.
    in_radius = [h for h in rows if h.get("distance_km") is not None
                 and h["distance_km"] <= radius_km]
    outside = [h for h in rows if h not in in_radius]
    nearest_outside = min((h["distance_km"] for h in outside
                           if h.get("distance_km") is not None), default=None)
    next_radius = next((r for r in (5, 10, 25, 100) if r > radius_km), None)

    return {"facilities": in_radius + outside,
            "in_radius": in_radius,
            "nearest_outside_km": nearest_outside,
            "next_radius_km": next_radius,
            "provider_failed": provider_failed,
            "data_source": data_source,
            "provider": settings_local.integration_status(),
            "search": {"lat": lat, "lng": lng, "location_text": location_text,
                       "query": query, "speciality": speciality,
                       "emergency": emergency, "multi_specialty": multi_specialty,
                       "highly_rated": highly_rated, "radius_km": radius_km},
            "ranking_factors": ["distance", "emergency capability", "public rating (when available)"],
            "disclaimer": "CareRoute discovery factors — not a quality endorsement. Live "
                          "bed/slot/ambulance availability is not available in this prototype.",
            **({"fallback_note": fallback_note} if fallback_note else {})}


@app.get("/places/status", tags=["system"])
def places_status(db: Session = Depends(get_db)):
    """Honest discovery-provider status for the UI."""
    provider = get_provider(db)
    return {"google_maps_configured": bool(settings.GOOGLE_MAPS_API_KEY),
            "provider": provider.name,
            "mode": provider.integration_status()["mode"],
            "data_source": provider.integration_status().get("data_source"),
            "message": {"GooglePlacesProvider":
                        "Dynamic discovery uses live Google Places data for any location.",
                        "OverpassProvider":
                        "Discovery uses live OpenStreetMap (Overpass) nearby search — real "
                        "mapped healthcare facilities around your coordinates, no API key needed.",
                        "PrototypeHospitalProvider":
                        "Demo provider mode: discovery runs on the controlled demo hospital "
                        "directory (development only)."}.get(provider.name, provider.name)}


@app.get("/hospitals/{hospital_id}", tags=["hospitals"])
def hospital_detail(hospital_id: int, lat: float | None = None, lng: float | None = None,
                    db: Session = Depends(get_db)):
    # Local numeric ids are the controlled DEMO hospitals used for the internal
    # appointment workflow — their detail always resolves from the CareRoute DB,
    # regardless of which live discovery provider is active. Live providers
    # (Overpass/Places) return self-contained results that never use this route.
    detail = PrototypeHospitalProvider().hospital_detail(db, hospital_id)
    if not detail:
        raise HTTPException(404, "Hospital not found")
    detail["distance_km"] = haversine_km(lat, lng, detail["latitude"], detail["longitude"])
    detail["workflow_note"] = ("Controlled demonstration hospital used for the CareRoute "
                               "appointment workflow — not a claim of live integration.")
    return detail


@app.get("/hospitals/{hospital_id}/availability/{kind}", tags=["hospitals"])
def hospital_live_availability(hospital_id: int, kind: str, db: Session = Depends(get_db)):
    """Live operational data through the provider abstraction. The prototype has no
    live feed, so the honest unavailable state is always returned — never invented."""
    if kind not in ("queue", "beds", "doctor_slots", "ambulance"):
        raise HTTPException(400, "Unknown availability kind")
    return get_provider(db).live_availability(db, hospital_id, kind)


@app.get("/doctors", tags=["doctors"])
def list_doctors(speciality: str | None = None, hospital_id: int | None = None,
                 db: Session = Depends(get_db)):
    q = db.query(DoctorHospitalAffiliation, Doctor).join(
        Doctor, DoctorHospitalAffiliation.doctor_id == Doctor.id)
    if speciality:
        q = q.filter(Doctor.speciality_key == speciality)
    if hospital_id:
        q = q.filter(DoctorHospitalAffiliation.hospital_id == hospital_id)
    out = []
    for aff, doc in q.all():
        hosp = db.get(Hospital, aff.hospital_id)
        dept = db.get(HospitalDepartment, aff.department_id) if aff.department_id else None
        out.append({"doctor_id": doc.id, "name": doc.name, "qualification": doc.qualification,
                    "speciality_key": doc.speciality_key,
                    "speciality_label": SPECIALITIES.get(doc.speciality_key, {}).get("label"),
                    "designation": doc.designation, "years_experience": doc.years_experience,
                    "verification_status": doc.verification_status, "profile_note": doc.profile_note,
                    "hospital_id": aff.hospital_id, "hospital_name": hosp.name if hosp else None,
                    "department_id": aff.department_id,
                    "department_name": dept.name if dept else None,
                    "opd_days": aff.opd_days,
                    "consultation_hours": aff.consultation_hours})
    return {"doctors": out}


# ============================================================== FIND CARE
@app.get("/find-care/specialities", tags=["find-care"])
def find_care_specialities():
    return {"specialities": [{"key": k, "label": v["label"]} for k, v in SPECIALITIES.items()]}


@app.post("/find-care/suggest", tags=["find-care"])
def find_care_suggest(body: dict):
    """Care navigation aid from the user's own description. NOT a diagnosis."""
    concern = str(body.get("concern", ""))[:500]
    suggestions = suggest_speciality(concern)
    return {"suggestions": suggestions, "is_diagnosis": False,
            "disclaimer": "This is care navigation help based on your description — not a "
                          "medical diagnosis. For emergencies, use the Emergency button."}


# ============================================================ APPOINTMENTS
class AppointmentRequest(BaseModel):
    patient_id: int | None = None          # required for caregiver/CHW on behalf
    doctor_id: int | None = None            # optional for a hospital-level request
    hospital_id: int | None = None
    department_id: int | None = None
    hospital_public: dict | None = None     # public place data for a live-discovered hospital
    appointment_date: date
    time_slot: str
    reason: str | None = None


@app.post("/appointments", tags=["appointments"])
def request_appointment(body: AppointmentRequest,
                        principal: Principal = Depends(get_current_principal),
                        db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    # A live public hospital can be selected even when its public source does not
    # expose departments/doctors. In that case this is a hospital-level request;
    # reception assigns the department/doctor later.
    doc = db.get(Doctor, body.doctor_id) if body.doctor_id else None
    hosp_id = body.hospital_id
    if not doc and body.doctor_id:
        raise HTTPException(404, "Doctor not found")

    if not hosp_id and body.hospital_public:
        hp = body.hospital_public
        name = str(hp.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "Hospital information is required")
        place_id = str(hp.get("place_id") or "").strip()
        existing = None
        if place_id:
            existing = db.query(Hospital).filter(Hospital.verified_fields.isnot(None)).all()
            existing = next((h for h in existing if isinstance(h.verified_fields, dict) and h.verified_fields.get("place_id") == place_id), None)
        if existing:
            hosp_id = existing.id
        else:
            h = Hospital(
                name=name[:200], hospital_type=str(hp.get("hospital_type") or "Hospital")[:40],
                address=str(hp.get("address") or "")[:300], city=str(hp.get("city") or "")[:80],
                pincode=str(hp.get("pincode") or "")[:12], latitude=hp.get("latitude"),
                longitude=hp.get("longitude"), phone=str(hp.get("phone") or "")[:24],
                emergency_phone=str(hp.get("emergency_phone") or "")[:24],
                website=str(hp.get("website") or "")[:160],
                description="Publicly discovered hospital/place used for CareRoute appointment-request routing.",
                data_source=str(hp.get("data_source") or "PUBLIC_DISCOVERY")[:40],
                verified_fields={"place_id": place_id, "public_source": True},
            )
            db.add(h); db.flush(); hosp_id = h.id

    if not hosp_id:
        raise HTTPException(400, "Select a hospital before requesting an appointment")

    # No public doctor directory? Create a non-login routing identity for reception.
    # This is not presented as a real doctor and is never exposed as a clinical doctor.
    if not doc:
        doc = db.query(Doctor).join(DoctorHospitalAffiliation, DoctorHospitalAffiliation.doctor_id == Doctor.id).filter(
            DoctorHospitalAffiliation.hospital_id == hosp_id, Doctor.user_id.is_(None),
            Doctor.name == "Hospital Appointment Desk").first()
        if not doc:
            doc = Doctor(name="Hospital Appointment Desk", qualification="Hospital appointment request",
                         speciality_key="general_medicine", designation="Reception routing",
                         verification_status="ROUTING_ONLY", profile_note="Not a clinical doctor; used only to route a demo appointment request to hospital reception.")
            db.add(doc); db.flush()
            db.add(DoctorHospitalAffiliation(doctor_id=doc.id, hospital_id=hosp_id))
            db.flush()
    behalf = {"USER": "SELF", "CAREGIVER": "CAREGIVER", "CHW": "CHW"}.get(principal.role)
    if not behalf:
        raise HTTPException(403, "Only users, caregivers and community workers can request appointments")

    # Resolve target patient + authorization.
    if principal.role == ROLE_USER:
        p = principal.own_patient()
        if not p:
            raise HTTPException(400, "Complete onboarding before requesting appointments")
    else:
        if not body.patient_id:
            raise HTTPException(400, "patient_id required when requesting on behalf of someone")
        p = patient_for_check(db, body.patient_id)
        if principal.role == ROLE_CAREGIVER:
            if "request_appointments" not in principal.caregiver_permissions(p.id):
                deny(principal, p.id, Access.APPOINTMENTS, meta, "caregiver appointment request")
        elif principal.role == ROLE_CHW:
            if p.id not in principal.assigned_patient_ids():
                deny(principal, p.id, Access.APPOINTMENTS, meta, "CHW appointment request")

    aff = db.query(DoctorHospitalAffiliation).filter(
        DoctorHospitalAffiliation.doctor_id == doc.id,
        DoctorHospitalAffiliation.hospital_id == hosp_id).first()
    dept_id = body.department_id if body.department_id else (aff.department_id if aff else None)
    if body.department_id:
        d_check = db.get(HospitalDepartment, body.department_id)
        if not d_check:
            raise HTTPException(404, "Department not found")
        if hosp_id and d_check.hospital_id != hosp_id:
            raise HTTPException(400, "Department does not belong to the selected hospital")
    conflict = db.query(Appointment).filter(
        Appointment.doctor_id == doc.id, Appointment.appointment_date == body.appointment_date,
        Appointment.time_slot == body.time_slot,
        Appointment.status.in_(["REQUESTED", "CONFIRMED"])).first()
    if conflict:
        raise HTTPException(409, "That slot is already taken. Please choose another time.")
    a = Appointment(patient_id=p.id, doctor_id=doc.id, hospital_id=hosp_id, department_id=dept_id,
                    requested_by_user_id=principal.id, requested_on_behalf=behalf,
                    appointment_date=body.appointment_date, time_slot=body.time_slot,
                    status="REQUESTED", reason=(body.reason or "")[:500])
    db.add(a)
    db.commit()
    db.refresh(a)
    audit(db, principal, "APPOINTMENT_REQUEST", patient_id=p.id, hospital_id=hosp_id,
          record_ref=f"appointment:{a.id}", purpose=body.reason, ip=meta.get("ip"))
    # Notify the target hospital staff. In demo mode, one student acting as reception
    # can receive requests for any publicly discovered hospital.
    staff_rows = db.query(HospitalStaff).filter(HospitalStaff.hospital_id == hosp_id).all()
    if settings.DEMO_APPOINTMENT_ROUTING and not staff_rows:
        staff_rows = db.query(HospitalStaff).all()
    for st in staff_rows:
        target = db.get(Hospital, hosp_id)
        target_name = target.name if target else "selected hospital"
        kind = "hospital appointment request" if doc.verification_status == "ROUTING_ONLY" else f"{SPECIALITIES.get(doc.speciality_key, {}).get('label', '')} appointment request"
        notify(db, st.user_id, "APPOINTMENT_REQUESTED", "New appointment request",
               f"{p.display_name} sent a {kind} for {target_name} on {body.appointment_date} {body.time_slot}.", a.id)
    if p.user_id:
        notify(db, p.user_id, "APPOINTMENT_REQUESTED", "Appointment request sent",
               f"Your request with {doc.name} on {body.appointment_date} is pending hospital confirmation.")
    return appointment_out(a, db)


@app.get("/appointments", tags=["appointments"])
def list_appointments(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    q = db.query(Appointment)
    if principal.role == ROLE_USER:
        p = principal.own_patient()
        if not p:
            return {"appointments": []}
        q = q.filter(Appointment.patient_id == p.id)
    elif principal.role == ROLE_CAREGIVER:
        pats = my_patients_rows(db, principal)
        ids = [pid for pid, perms in pats if "view_appointments" in perms]
        q = q.filter(Appointment.patient_id.in_(ids or [-1]))
    elif principal.role == ROLE_DOCTOR:
        # Doctors see only appointments that hospital staff have actually confirmed,
        # plus their own completed consultations. Pending patient requests remain in
        # the hospital staff workflow until reception confirms them. This prevents
        # the doctor dashboard from becoming a static/premature patient directory.
        q = q.filter(
            Appointment.doctor_id == principal.doctor.id,
            Appointment.status.in_(["CONFIRMED", "COMPLETED"])
        )
    elif principal.role == ROLE_STAFF:
        if not settings.DEMO_APPOINTMENT_ROUTING:
            q = q.filter(Appointment.hospital_id == principal.staff_hospital_id)
    elif principal.role == ROLE_ADMIN:
        q = q.filter(Appointment.hospital_id == principal.admin_hospital_id)
    elif principal.role == ROLE_CHW:
        ids = principal.assigned_patient_ids()
        q = q.filter(Appointment.patient_id.in_(ids or [-1]))
    items = q.order_by(Appointment.appointment_date.desc()).limit(100).all()
    return {"appointments": [appointment_out(a, db) for a in items]}


@app.get("/appointments/{appointment_id}", tags=["appointments"])
def get_appointment(appointment_id: int, principal: Principal = Depends(get_current_principal),
                    db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    a = db.get(Appointment, appointment_id)
    if not a:
        raise HTTPException(404, "Appointment not found")
    allowed = (
        (principal.role in (ROLE_USER, ROLE_CAREGIVER) and principal.own_patient()
         and principal.own_patient().id == a.patient_id)
        or (principal.role == ROLE_DOCTOR and principal.doctor and a.doctor_id == principal.doctor.id)
        or (principal.role == ROLE_STAFF and a.hospital_id == principal.staff_hospital_id)
        or (principal.role == ROLE_ADMIN and a.hospital_id == principal.admin_hospital_id)
        or (principal.role == ROLE_CHW and a.patient_id in principal.assigned_patient_ids()))
    if not allowed:
        deny(principal, a.patient_id, Access.APPOINTMENTS, meta, "appointment detail")
    audit(db, principal, "VIEW_APPOINTMENTS", patient_id=a.patient_id, hospital_id=a.hospital_id,
          record_ref=f"appointment:{a.id}", ip=meta.get("ip"))
    return appointment_out(a, db)


class StaffDecision(BaseModel):
    note: str | None = None
    new_date: date | None = None
    new_slot: str | None = None


def _staff_hospital_gate(principal, a: Appointment):
    if principal.role == ROLE_STAFF and settings.DEMO_APPOINTMENT_ROUTING:
        return
    if principal.role == ROLE_STAFF and a.hospital_id == principal.staff_hospital_id:
        return
    if principal.role == ROLE_ADMIN and a.hospital_id == principal.admin_hospital_id:
        return
    raise HTTPException(403, "Appointment management is handled by hospital staff")


@app.post("/appointments/{appointment_id}/confirm", tags=["appointments"])
def confirm_appointment(appointment_id: int, body: StaffDecision,
                        principal: Principal = Depends(require_roles(ROLE_STAFF, ROLE_ADMIN)),
                        db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    a = db.get(Appointment, appointment_id)
    if not a or a.status not in ("REQUESTED", "RESCHEDULED"):
        raise HTTPException(404, "Pending appointment not found")
    _staff_hospital_gate(principal, a)
    a.status = "CONFIRMED"
    a.staff_note = body.note
    a.token_number = f"T-{a.id:02d}"
    a.updated_at = datetime.utcnow()
    db.commit()
    pat = db.get(Patient, a.patient_id)
    doc = db.get(Doctor, a.doctor_id)
    audit(db, principal, "APPOINTMENT_CONFIRM", patient_id=a.patient_id, hospital_id=a.hospital_id,
          record_ref=f"appointment:{a.id}", ip=meta.get("ip"))
    if pat.user_id:
        notify(db, pat.user_id, "APPOINTMENT_CONFIRMED", "Appointment confirmed",
               f"{doc.name} on {a.appointment_date} at {a.time_slot} is confirmed. Token {a.token_number}.")
    for c in db.query(CaregiverRelationship).filter(
            CaregiverRelationship.patient_id == a.patient_id, CaregiverRelationship.status == "ACTIVE"):
        notify(db, c.caregiver_user_id, "APPOINTMENT_CONFIRMED", "Appointment confirmed",
               f"Appointment with {doc.name} on {a.appointment_date} {a.time_slot} confirmed.")
    return appointment_out(a, db)


@app.post("/appointments/{appointment_id}/reject", tags=["appointments"])
def reject_appointment(appointment_id: int, body: StaffDecision,
                       principal: Principal = Depends(require_roles(ROLE_STAFF, ROLE_ADMIN)),
                       db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    a = db.get(Appointment, appointment_id)
    if not a or a.status not in ("REQUESTED", "RESCHEDULED"):
        raise HTTPException(404, "Pending appointment not found")
    _staff_hospital_gate(principal, a)
    a.status = "REJECTED"
    a.staff_note = body.note or "Rejected"
    a.updated_at = datetime.utcnow()
    db.commit()
    pat = db.get(Patient, a.patient_id)
    audit(db, principal, "APPOINTMENT_REJECT", patient_id=a.patient_id, hospital_id=a.hospital_id,
          record_ref=f"appointment:{a.id}", detail=body.note, ip=meta.get("ip"))
    if pat.user_id:
        notify(db, pat.user_id, "APPOINTMENT_REJECTED", "Appointment request rejected",
               f"Your appointment request was rejected by the hospital. Reason: {a.staff_note}")
    return appointment_out(a, db)


class AcceptRescheduleBody(BaseModel):
    patient_id: int | None = None   # required when acting as caregiver/CHW on behalf


@app.post("/appointments/{appointment_id}/accept-reschedule", tags=["appointments"])
def accept_reschedule(appointment_id: int, body: AcceptRescheduleBody,
                      principal: Principal = Depends(get_current_principal),
                      db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    """Patient (or authorized caregiver/CHW) accepts a staff-suggested alternative time.
    The appointment only becomes CONFIRMED after this explicit patient action."""
    a = db.get(Appointment, appointment_id)
    if not a or a.status != "RESCHEDULED":
        raise HTTPException(404, "No suggested alternative time pending for this appointment")
    if principal.role == ROLE_USER:
        p = principal.own_patient()
        if not p or p.id != a.patient_id:
            deny(principal, a.patient_id, Access.APPOINTMENTS, meta, "accept reschedule")
    elif principal.role in (ROLE_CAREGIVER, ROLE_CHW):
        if not body.patient_id:
            raise HTTPException(400, "patient_id required when acting on behalf of someone")
        if principal.role == ROLE_CAREGIVER:
            if "request_appointments" not in principal.caregiver_permissions(a.patient_id):
                deny(principal, a.patient_id, Access.APPOINTMENTS, meta, "accept reschedule")
        else:
            if a.patient_id not in principal.assigned_patient_ids():
                deny(principal, a.patient_id, Access.APPOINTMENTS, meta, "accept reschedule")
    else:
        raise HTTPException(403, "Only the patient (or authorized assistant) can accept a reschedule")
    a.status = "CONFIRMED"
    a.token_number = f"T-{a.id:02d}"
    a.updated_at = datetime.utcnow()
    db.commit()
    doc = db.get(Doctor, a.doctor_id)
    audit(db, principal, "APPOINTMENT_RESCHEDULE_ACCEPTED", patient_id=a.patient_id,
          hospital_id=a.hospital_id, record_ref=f"appointment:{a.id}", ip=meta.get("ip"))
    staff_h = db.query(HospitalStaff).filter(HospitalStaff.hospital_id == a.hospital_id).all()
    for st in staff_h:
        notify(db, st.user_id, "APPOINTMENT_RESCHEDULE_ACCEPTED", "Patient accepted new time",
               f"{db.get(Patient, a.patient_id).display_name} accepted the alternative time "
               f"{a.appointment_date} {a.time_slot} with {doc.name}.")
    if db.get(Patient, a.patient_id).user_id:
        notify(db, db.get(Patient, a.patient_id).user_id, "APPOINTMENT_CONFIRMED",
               "Appointment confirmed",
               f"You accepted the new time — {doc.name} on {a.appointment_date} {a.time_slot}. "
               f"Token {a.token_number}.")
    return appointment_out(a, db)


@app.post("/appointments/{appointment_id}/reschedule", tags=["appointments"])
def reschedule_appointment(appointment_id: int, body: StaffDecision,
                           principal: Principal = Depends(require_roles(ROLE_STAFF, ROLE_ADMIN)),
                           db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    a = db.get(Appointment, appointment_id)
    if not a or a.status not in ("REQUESTED", "CONFIRMED", "RESCHEDULED"):
        raise HTTPException(404, "Appointment not found")
    _staff_hospital_gate(principal, a)
    if not body.new_date or not body.new_slot:
        raise HTTPException(400, "new_date and new_slot are required")
    moved = Appointment(
        patient_id=a.patient_id, doctor_id=a.doctor_id, hospital_id=a.hospital_id,
        department_id=a.department_id, requested_by_user_id=a.requested_by_user_id,
        requested_on_behalf=a.requested_on_behalf, appointment_date=body.new_date,
        time_slot=body.new_slot, status="RESCHEDULED", reason=a.reason,
        staff_note=body.note, rescheduled_from_id=a.id)
    db.add(moved)
    a.status = "RESCHEDULED_MOVED"
    a.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(moved)
    pat = db.get(Patient, a.patient_id)
    doc = db.get(Doctor, a.doctor_id)
    audit(db, principal, "APPOINTMENT_RESCHEDULE", patient_id=a.patient_id,
          hospital_id=a.hospital_id, record_ref=f"appointment:{moved.id}",
          detail=f"from {a.appointment_date} {a.time_slot} to {body.new_date} {body.new_slot}",
          ip=meta.get("ip"))
    if pat.user_id:
        notify(db, pat.user_id, "APPOINTMENT_RESCHEDULED", "Appointment rescheduled",
               f"{doc.name}'s appointment moved to {body.new_date} {body.new_slot}. "
               f"Awaiting your confirmation request update.")
    return appointment_out(moved, db)


class ConsultationNote(BaseModel):
    notes: str
    diagnosis_text: str | None = None


@app.post("/appointments/{appointment_id}/complete", tags=["appointments"])
def complete_appointment(appointment_id: int, body: ConsultationNote,
                         principal: Principal = Depends(require_roles(ROLE_DOCTOR)),
                         db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    a = db.get(Appointment, appointment_id)
    if not a or a.doctor_id != principal.doctor.id:
        raise HTTPException(404, "Appointment not found in your schedule")
    if a.status not in ("CONFIRMED", "RESCHEDULED"):
        raise HTTPException(400, "Only confirmed appointments can be completed")
    a.status = "COMPLETED"
    a.staff_note = body.notes[:1000]
    a.updated_at = datetime.utcnow()
    db.commit()
    audit(db, principal, "CONSULTATION_NOTE", patient_id=a.patient_id, hospital_id=a.hospital_id,
          record_ref=f"appointment:{a.id}", ip=meta.get("ip"))
    return appointment_out(a, db)


# =========================================================== HEALTH MEMORY
def _patient_access_or_denied(principal: Principal, patient_id: int, resource: str,
                              meta: dict, purpose: str, context: dict | None = None) -> Patient:
    p = patient_for_check(principal.db, patient_id)
    if not principal.can_access(patient_id, resource, context):
        deny(principal, patient_id, resource, meta, purpose)
    return p


@app.get("/health-memory/{patient_id}", tags=["health-memory"])
def health_memory(patient_id: int, principal: Principal = Depends(get_current_principal),
                  db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    p = patient_for_check(principal.db, patient_id)
    caregiver_perms: set[str] | None = None
    if principal.role == ROLE_CAREGIVER:
        caregiver_perms = principal.caregiver_permissions(patient_id)
        if not ({"view_health_logs", "view_medications"} & caregiver_perms):
            deny(principal, patient_id, Access.CONDITIONS, meta, "caregiver health memory view")
    elif not principal.can_access(patient_id, Access.CONDITIONS, None):
        deny(principal, patient_id, Access.CONDITIONS, meta, "health memory view")
    audit(db, principal, "VIEW_HEALTH_LOG", patient_id=patient_id, record_ref="health_memory",
          ip=meta.get("ip"))

    def _timeline() -> list[dict]:
        """Chronological Health Memory timeline from real records ONLY —
        every entry cites the record that produced it; nothing is invented."""
        events: list[dict] = []
        for c in conditions:
            events.append({"date": str(c.diagnosed_on or c.id), "kind": "condition",
                           "title": f"Condition recorded: {c.condition}",
                           "detail": (f"status {c.status}" + (f" — {c.notes}" if c.notes else "")),
                           "source": "USER_REPORTED" if c.source == "USER_REPORTED" else "care team",
                           "ref": f"condition:{c.id}"})
        for l in logs:
            bits = []
            if l.pain_level is not None: bits.append(f"pain {l.pain_level}/10")
            if l.symptoms: bits.append(l.symptoms)
            if l.mood: bits.append(f"feeling {l.mood.lower()}")
            events.append({"date": str(l.logged_at.date()), "kind": "log",
                           "title": "Daily medical log", "detail": " · ".join(bits) or "—",
                           "source": "patient entry", "ref": f"health_log:{l.id}"})
        for ap in db.query(Appointment).filter(Appointment.patient_id == patient_id).all():
            doc = db.get(Doctor, ap.doctor_id)
            hosp = db.get(Hospital, ap.hospital_id)
            events.append({"date": str(ap.appointment_date), "kind": "appointment",
                           "title": f"{ap.status.title()} appointment — {doc.name if doc else 'Doctor'}",
                           "detail": f"{hosp.name if hosp else ''} · {ap.time_slot}".strip(" ·"),
                           "source": "appointment record", "ref": f"appointment:{ap.id}"})
        for rx in db.query(Prescription).filter(Prescription.patient_id == patient_id).all():
            doc = db.get(Doctor, rx.doctor_id)
            events.append({"date": str(rx.issued_at.date()), "kind": "prescription",
                           "title": f"Prescription issued by {doc.name if doc else 'doctor'}",
                           "detail": (rx.diagnosis_text or "")[:120],
                           "source": "doctor workflow", "ref": f"prescription:{rx.id}"})
        for r in db.query(MedicalReport).filter(MedicalReport.patient_id == patient_id).all():
            events.append({"date": str(r.report_date), "kind": "report",
                           "title": f"{r.report_type.title()} report — {r.title}",
                           "detail": (r.summary or "")[:120],
                           "source": r.data_source or "PROTOTYPE_UPLOAD", "ref": f"report:{r.id}"})
        for ev in events:
            ev["date"] = str(ev["date"])[:10]
        return sorted(events, key=lambda e: e["date"], reverse=True)[:60]

    conditions = db.query(MedicalCondition).filter(MedicalCondition.patient_id == patient_id).all()
    allergies = db.query(Allergy).filter(Allergy.patient_id == patient_id).all()
    medications = db.query(Medication).filter(Medication.patient_id == patient_id).all()
    logs = db.query(HealthLog).filter(HealthLog.patient_id == patient_id).order_by(
        HealthLog.logged_at.desc()).limit(30).all()
    resp = {
        "patient": {"id": patient_id},
        "timeline": _timeline(),
        "conditions": [{"id": c.id, "condition": c.condition, "speciality_key": c.speciality_key,
                        "diagnosed_on": str(c.diagnosed_on) if c.diagnosed_on else None,
                        "status": c.status, "notes": c.notes, "source": c.source} for c in conditions],
        "allergies": [{"id": a.id, "allergen": a.allergen, "severity": a.severity,
                       "reaction": a.reaction} for a in allergies],
        "medications": [{"id": m.id, "name": m.name, "dosage": m.dosage, "frequency": m.frequency,
                         "start_date": str(m.start_date) if m.start_date else None,
                         "end_date": str(m.end_date) if m.end_date else None, "status": m.status,
                         "prescribed_by": m.prescribed_by,
                         "last_taken_on": str(m.last_taken_on) if m.last_taken_on else None} for m in medications],
        "health_logs": [{"id": l.id, "logged_at": str(l.logged_at), "pain_level": l.pain_level,
                         "temperature_c": l.temperature_c, "mood": l.mood, "symptoms": l.symptoms,
                         "adherence": l.adherence, "notes": l.notes} for l in logs],
    }
    if caregiver_perms is not None:
        # Minimum-necessary caregiver view: only explicitly granted sections are returned.
        resp["conditions"], resp["allergies"] = [], []
        if "view_medications" not in caregiver_perms:
            resp["medications"] = []
        if "view_health_logs" not in caregiver_perms:
            resp["health_logs"] = []
        resp["scope_note"] = ("Limited caregiver view — only sections the patient explicitly "
                              "authorized are included.")
    return resp


class ConditionIn(BaseModel):
    condition: str
    speciality_key: str | None = None
    diagnosed_on: date | None = None
    notes: str | None = None


class AllergyIn(BaseModel):
    allergen: str
    severity: str = "MODERATE"
    reaction: str | None = None


class HealthLogIn(BaseModel):
    pain_level: int | None = Field(default=None, ge=0, le=10)
    temperature_c: float | None = None
    mood: str | None = None
    symptoms: str | None = None
    adherence: str | None = None
    notes: str | None = None


def my_patients_rows(db: Session, principal: Principal) -> list[tuple[int, set[str]]]:
    """Caregiver scope: (patient_id, granted_permissions) for ACTIVE relationships."""
    rels = db.query(CaregiverRelationship).filter(
        CaregiverRelationship.caregiver_user_id == principal.id,
        CaregiverRelationship.status == "ACTIVE").all()
    return [(r.patient_id, principal.caregiver_permissions(r.patient_id)) for r in rels]


def _self_patient(principal: Principal) -> Patient:
    if principal.role != ROLE_USER:
        raise HTTPException(403, "Only the account owner can modify health memory")
    p = principal.own_patient()
    if not p:
        raise HTTPException(400, "Complete onboarding first")
    return p


@app.post("/health-memory/conditions", tags=["health-memory"])
def add_condition(body: ConditionIn, principal: Principal = Depends(get_current_principal),
                  db: Session = Depends(get_db)):
    p = _self_patient(principal)
    c = MedicalCondition(patient_id=p.id, condition=body.condition[:200],
                         speciality_key=body.speciality_key or _guess_speciality(body.condition),
                         diagnosed_on=body.diagnosed_on, notes=body.notes, source="USER_REPORTED")
    db.add(c)
    db.commit()
    return {"id": c.id}


@app.post("/health-memory/allergies", tags=["health-memory"])
def add_allergy(body: AllergyIn, principal: Principal = Depends(get_current_principal),
                db: Session = Depends(get_db)):
    p = _self_patient(principal)
    a = Allergy(patient_id=p.id, allergen=body.allergen[:120], severity=body.severity,
                reaction=body.reaction)
    db.add(a)
    db.commit()
    return {"id": a.id}


@app.post("/health-memory/logs", tags=["health-memory"])
def add_health_log(body: HealthLogIn, principal: Principal = Depends(get_current_principal),
                   db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    p = _self_patient(principal)
    l = HealthLog(patient_id=p.id, pain_level=body.pain_level, temperature_c=body.temperature_c,
                  mood=(body.mood or "")[:40], symptoms=body.symptoms,
                  adherence=(body.adherence or "TAKEN_ALL"), notes=body.notes)
    db.add(l)
    db.commit()
    audit(db, principal, "VIEW_HEALTH_LOG", patient_id=p.id, record_ref="health_log:create",
          ip=meta.get("ip"))
    return {"id": l.id}


@app.get("/health-memory/{patient_id}/trends", tags=["health-memory"])
def health_trends(patient_id: int, principal: Principal = Depends(get_current_principal),
                  db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    _patient_access_or_denied(principal, patient_id, Access.HEALTH_LOGS, meta, "health trends")
    logs = db.query(HealthLog).filter(HealthLog.patient_id == patient_id).order_by(
        HealthLog.logged_at.asc()).limit(30).all()
    return {"trend": [{"date": str(l.logged_at.date()), "pain_level": l.pain_level,
                       "temperature_c": l.temperature_c} for l in logs]}


@app.get("/health-memory/{patient_id}/summary", tags=["health-memory"])
def health_memory_summary(patient_id: int, principal: Principal = Depends(get_current_principal),
                          db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    """AI summarization on pre-authorized, filtered information only."""
    p = _patient_access_or_denied(principal, patient_id, Access.SNAPSHOT, meta,
                                  "AI health memory summary")
    # §18: with no stored activity there is nothing to summarize — say so honestly
    # instead of generating a generic paragraph.
    has_activity = (db.query(HealthLog).filter(HealthLog.patient_id == patient_id).count() > 0
                    or db.query(Appointment).filter(Appointment.patient_id == patient_id).count() > 0
                    or db.query(Prescription).filter(Prescription.patient_id == patient_id).count() > 0)
    if not has_activity:
        audit(db, principal, "AI_SUMMARY_REQUESTED", patient_id=patient_id,
              record_ref="health_memory", purpose="health memory summarization (insufficient history)",
              ip=meta.get("ip"))
        return {"summary": None,
                "insufficient_history": True,
                "message": "Not enough historical information to generate a meaningful "
                           "Health Memory. It will develop as you add medical logs, "
                           "appointments, prescriptions and health records.",
                "engine": "deterministic_summarizer", "ai_generated": False}
    info = {
        "patient_name": p.display_name,
        "conditions": [{"condition": c.condition, "status": c.status}
                       for c in db.query(MedicalCondition).filter(
                           MedicalCondition.patient_id == patient_id).all()],
        "medications": [{"name": m.name, "dosage": m.dosage, "frequency": m.frequency,
                         "status": m.status}
                        for m in db.query(Medication).filter(Medication.patient_id == patient_id).all()],
        "recent_logs": [{"pain_level": l.pain_level, "symptoms": l.symptoms, "mood": l.mood}
                        for l in db.query(HealthLog).filter(
                            HealthLog.patient_id == patient_id).order_by(
                            HealthLog.logged_at.desc()).limit(10).all()],
    }
    result = ai_service.summarize_health_memory(info)
    audit(db, principal, "AI_SUMMARY_REQUESTED", patient_id=patient_id, record_ref="health_memory",
          purpose="health memory summarization", ip=meta.get("ip"))
    return result


# ============================================================= MEDICATIONS
class MedicationIn(BaseModel):
    name: str
    dosage: str | None = None
    frequency: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None


@app.post("/medications", tags=["medications"])
def add_medication(body: MedicationIn, principal: Principal = Depends(get_current_principal),
                   db: Session = Depends(get_db)):
    p = _self_patient(principal)
    m = Medication(patient_id=p.id, name=body.name[:160], dosage=body.dosage, frequency=body.frequency,
                   start_date=body.start_date or date.today(), end_date=body.end_date,
                   status="ACTIVE", prescribed_by="Self-recorded", notes=body.notes)
    db.add(m)
    db.commit()
    return {"id": m.id}


@app.post("/medications/{medication_id}/taken", tags=["medications"])
def mark_medication_taken(medication_id: int,
                          principal: Principal = Depends(get_current_principal),
                          db: Session = Depends(get_db)):
    """Patient (or authorized caregiver with assist_medication) records a dose taken today."""
    p = _self_patient(principal)
    m = db.query(Medication).filter(Medication.id == medication_id,
                                    Medication.patient_id == p.id).first()
    if not m:
        raise HTTPException(404, "Medication not found")
    m.last_taken_on = date.today()
    db.commit()
    return {"id": m.id, "last_taken_on": str(m.last_taken_on)}


@app.patch("/medications/{medication_id}", tags=["medications"])
def update_medication(medication_id: int, body: dict,
                      principal: Principal = Depends(get_current_principal),
                      db: Session = Depends(get_db)):
    p = _self_patient(principal)
    m = db.query(Medication).filter(Medication.id == medication_id,
                                    Medication.patient_id == p.id).first()
    if not m:
        raise HTTPException(404, "Medication not found")
    if body.get("status") in ("ACTIVE", "COMPLETED", "PAUSED"):
        m.status = body["status"]
    if body.get("end_date"):
        m.end_date = body["end_date"]
    db.commit()
    return {"id": m.id, "status": m.status}


# =========================================================== PRESCRIPTIONS
@app.get("/prescriptions", tags=["prescriptions"])
def list_prescriptions(patient_id: int | None = None,
                       principal: Principal = Depends(get_current_principal),
                       db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    if principal.role == ROLE_USER:
        p = principal.own_patient()
        if not p:
            return {"prescriptions": []}
        target = p.id
    elif principal.role == ROLE_CAREGIVER:
        pats = my_patients_rows(db, principal)
        target = next((pid for pid, perms in pats if "view_prescriptions" in perms), None)
        if not target:
            raise HTTPException(403, "Prescription access has not been granted to you")
    elif principal.role == ROLE_DOCTOR:
        if not patient_id:
            raise HTTPException(400, "patient_id required")
        _patient_access_or_denied(principal, patient_id, Access.PRESCRIPTIONS, meta,
                                  "doctor prescriptions view")
        target = patient_id
    else:
        raise HTTPException(403, "Prescriptions are not part of this role's scope")
    rows = db.query(Prescription).filter(Prescription.patient_id == target).order_by(
        Prescription.issued_at.desc()).all()
    out = []
    for r in rows:
        doc = db.get(Doctor, r.doctor_id)
        hosp = db.get(Hospital, r.hospital_id)
        out.append({"id": r.id, "issued_at": str(r.issued_at),
                    "doctor_name": doc.name if doc else None,
                    "qualification": doc.qualification if doc else None,
                    "hospital_name": hosp.name if hosp else None,
                    "diagnosis_text": r.diagnosis_text, "instructions": r.instructions,
                    "follow_up_on": str(r.follow_up_on) if r.follow_up_on else None,
                    "items": [{"medicine": i.medicine, "dosage": i.dosage, "frequency": i.frequency,
                               "duration_days": i.duration_days, "instructions": i.instructions}
                              for i in r.items]})
    if principal.role != ROLE_USER:
        audit(db, principal, "VIEW_PRESCRIPTION", patient_id=target, record_ref="prescriptions:list",
              ip=meta.get("ip"))
    return {"prescriptions": out}


class PrescriptionIn(BaseModel):
    patient_id: int
    appointment_id: int | None = None
    diagnosis_text: str | None = None
    instructions: str | None = None
    follow_up_on: date | None = None
    items: list[dict]


@app.post("/prescriptions", tags=["prescriptions"])
def create_prescription(body: PrescriptionIn,
                        principal: Principal = Depends(require_roles(ROLE_DOCTOR)),
                        db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    p = patient_for_check(db, body.patient_id)
    if not principal.can_access(body.patient_id, Access.PRESCRIPTIONS,
                                {"appointment_id": body.appointment_id}):
        deny(principal, body.patient_id, Access.PRESCRIPTIONS, meta, "prescription creation")
    rx = Prescription(patient_id=p.id, doctor_id=principal.doctor.id,
                      hospital_id=principal.doctor_affiliations[0].hospital_id
                      if principal.doctor_affiliations else None,
                      appointment_id=body.appointment_id, diagnosis_text=(body.diagnosis_text or "")[:300],
                      instructions=body.instructions, follow_up_on=body.follow_up_on)
    db.add(rx)
    db.flush()
    for item in body.items[:20]:
        if not item.get("medicine"):
            continue
        db.add(PrescriptionItem(prescription_id=rx.id, medicine=str(item["medicine"])[:160],
                                dosage=item.get("dosage"), frequency=item.get("frequency"),
                                duration_days=item.get("duration_days"),
                                instructions=item.get("instructions")))
    db.commit()
    db.refresh(rx)
    audit(db, principal, "PRESCRIPTION_CREATED", patient_id=p.id, hospital_id=rx.hospital_id,
          record_ref=f"prescription:{rx.id}", ip=meta.get("ip"))
    if p.user_id:
        notify(db, p.user_id, "PRESCRIPTION_AVAILABLE", "New prescription available",
               f"Dr. {principal.user.name} issued a prescription"
               + (" with follow-up on " + str(body.follow_up_on) if body.follow_up_on else "."))
    return {"id": rx.id, "issued_at": str(rx.issued_at), "items_added": len(rx.items)}


# ================================================================ REPORTS
@app.get("/reports", tags=["reports"])
def list_reports(patient_id: int | None = None, speciality_key: str | None = None,
                 principal: Principal = Depends(get_current_principal),
                 db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    if principal.role == ROLE_USER:
        p = principal.own_patient()
        if not p:
            return {"reports": []}
        target = p.id
    elif principal.role == ROLE_CAREGIVER:
        # Reports are sensitive records: caregivers have no permission key by design.
        pats = my_patients_rows(db, principal)
        target = next((pid for pid, _ in pats), None)
        if target:
            deny(principal, target, Access.REPORTS, meta, "caregiver reports")
        return {"reports": []}
    elif principal.role == ROLE_DOCTOR:
        if not patient_id:
            raise HTTPException(400, "patient_id required")
        _patient_access_or_denied(principal, patient_id, Access.REPORTS, meta,
                                  "doctor reports view", {"speciality_key": speciality_key})
        target = patient_id
    else:
        raise HTTPException(403, "Reports are not part of this role's scope")
    q = db.query(MedicalReport).filter(MedicalReport.patient_id == target)
    if speciality_key and principal.role == ROLE_DOCTOR:
        q = q.filter(MedicalReport.speciality_key == speciality_key)
    rows = q.order_by(MedicalReport.report_date.desc()).all()
    if principal.role != ROLE_USER:
        audit(db, principal, "VIEW_REPORT", patient_id=target, record_ref="reports:list",
              ip=meta.get("ip"))
    return {"reports": [{"id": r.id, "title": r.title, "report_type": r.report_type,
                         "speciality_key": r.speciality_key, "report_date": str(r.report_date),
                         "summary": r.summary, "findings": r.findings, "file_name": r.file_name,
                         "data_source": r.data_source} for r in rows]}


@app.post("/reports", tags=["reports"])
async def upload_report(title: str = Form(...), report_type: str = Form("DOCUMENT"),
                        speciality_key: str = Form("general_medicine"),
                        file: UploadFile = File(...),
                        principal: Principal = Depends(get_current_principal),
                        db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    p = _self_patient(principal)
    if not title.strip():
        raise HTTPException(400, "Title is required")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 5 MB)")
    r = MedicalReport(patient_id=p.id, title=title.strip()[:200], report_type=report_type,
                      speciality_key=speciality_key, report_date=date.today(),
                      file_name=file.filename[:200], content_type=file.content_type or "application/octet-stream",
                      file_data=data, data_source="USER_UPLOAD")
    db.add(r)
    db.commit()
    audit(db, principal, "VIEW_REPORT", patient_id=p.id, record_ref=f"report:{r.id}",
          purpose="report upload", ip=meta.get("ip"))
    return {"id": r.id, "title": r.title}


@app.get("/reports/{report_id}/file", tags=["reports"])
def download_report(report_id: int, principal: Principal = Depends(get_current_principal),
                    db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    r = db.get(MedicalReport, report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    allowed = (principal.role == ROLE_USER and principal.own_patient()
               and principal.own_patient().id == r.patient_id)
    if not allowed and principal.role == ROLE_DOCTOR:
        allowed = principal.can_access(r.patient_id, Access.REPORTS,
                                       {"speciality_key": r.speciality_key})
    if not allowed:
        deny(principal, r.patient_id, Access.REPORTS, meta, "report file download")
    audit(db, principal, "VIEW_REPORT", patient_id=r.patient_id, record_ref=f"report:{r.id}",
          purpose="report file download", ip=meta.get("ip"))
    return Response(content=r.file_data or b"", media_type=r.content_type or "application/octet-stream",
                    headers={"Content-Disposition": f'inline; filename="{r.file_name}"'})


# ===================================================== CLINICAL SNAPSHOT
@app.get("/clinical-snapshot/{patient_id}", tags=["clinical-snapshot"])
def clinical_snapshot(patient_id: int, speciality_key: str | None = None,
                      purpose: str = "consultation",
                      principal: Principal = Depends(get_current_principal),
                      db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    """Speciality-filtered Clinical Snapshot. Access decided by the authorization
    engine; the AI only receives the filtered subset produced here."""
    doc_speciality = principal.doctor.speciality_key if principal.doctor else speciality_key
    context = {"speciality_key": speciality_key or doc_speciality, "purpose": purpose}
    p = _patient_access_or_denied(principal, patient_id, Access.SNAPSHOT, meta,
                                  f"clinical snapshot ({purpose})", context)
    skey = speciality_key or doc_speciality
    conditions = db.query(MedicalCondition).filter(MedicalCondition.patient_id == patient_id).all()
    relevant_conditions = [c for c in conditions if not skey or c.speciality_key == skey
                           or c.status == "ACTIVE"] if skey else conditions
    allergies = db.query(Allergy).filter(Allergy.patient_id == patient_id).all()
    meds = db.query(Medication).filter(Medication.patient_id == patient_id,
                                       Medication.status == "ACTIVE").all()
    reports_q = db.query(MedicalReport).filter(MedicalReport.patient_id == patient_id)
    if skey and principal.role == ROLE_DOCTOR:
        reports_q = reports_q.filter(MedicalReport.speciality_key == skey)
    reports = reports_q.order_by(MedicalReport.report_date.desc()).limit(6).all()
    logs = db.query(HealthLog).filter(HealthLog.patient_id == patient_id).order_by(
        HealthLog.logged_at.desc()).limit(7).all()
    appts = db.query(Appointment).filter(
        Appointment.patient_id == patient_id, Appointment.status == "COMPLETED").order_by(
        Appointment.appointment_date.desc()).limit(5).all()

    if principal.role == ROLE_DOCTOR:
        audit(db, principal, "VIEW_CLINICAL_SNAPSHOT", patient_id=patient_id,
              record_ref=f"snapshot:{skey or 'all'}", purpose=purpose, ip=meta.get("ip"))

    snapshot = {
        "patient": {"display_name": p.display_name, "age": _age(p.date_of_birth),
                    "blood_group": p.blood_group, "preferred_language": p.preferred_language},
        "speciality_filter": skey,
        "conditions": [{"condition": c.condition, "status": c.status,
                        "speciality_key": c.speciality_key,
                        "diagnosed_on": str(c.diagnosed_on) if c.diagnosed_on else None,
                        "in_scope": (not skey) or c.speciality_key == skey} for c in relevant_conditions],
        "allergies": [{"allergen": a.allergen, "severity": a.severity, "reaction": a.reaction}
                      for a in allergies],
        "medications": [{"name": m.name, "dosage": m.dosage, "frequency": m.frequency}
                        for m in meds],
        "reports": [{"id": r.id, "title": r.title, "report_type": r.report_type,
                     "report_date": str(r.report_date), "summary": r.summary} for r in reports],
        "recent_symptoms": [{"date": str(l.logged_at.date()), "symptoms": l.symptoms,
                             "pain_level": l.pain_level} for l in logs],
        "relevant_consultations": appointment_out_appts(db, appts),
    }
    ai = ai_service.generate_clinical_snapshot(
        {"conditions": [c["condition"] for c in snapshot["conditions"]],
         "allergies": snapshot["allergies"],
         "medications": snapshot["medications"],
         "reports": [{"title": r["title"], "summary": r["summary"]} for r in snapshot["reports"]],
         "recent_symptoms": [s["symptoms"] for s in snapshot["recent_symptoms"] if s["symptoms"]]},
        SPECIALITIES.get(skey, {}).get("label", "General") if skey else "Overall")
    snapshot["ai_summary"] = ai
    return snapshot


def appointment_out_appts(db: Session, appts: list[Appointment]) -> list[dict]:
    out = []
    for a in appts:
        doc = db.get(Doctor, a.doctor_id)
        hosp = db.get(Hospital, a.hospital_id)
        out.append({"date": str(a.appointment_date), "doctor": doc.name if doc else None,
                    "hospital": hosp.name if hosp else None, "reason": a.reason})
    return out


def _age(dob) -> int | None:
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# ======================================================== CAREGIVER ACCESS
@app.get("/caregivers", tags=["caregivers"])
def list_caregivers(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    if principal.role != ROLE_USER:
        raise HTTPException(403, "Only account owners manage caregiver access")
    p = principal.own_patient()
    if not p:
        return {"caregivers": []}
    rels = db.query(CaregiverRelationship).filter(
        CaregiverRelationship.patient_id == p.id).all()
    out = []
    for rel in rels:
        cg_user = db.get(User, rel.caregiver_user_id)
        perms = db.query(CaregiverPermission).filter(
            CaregiverPermission.relationship_id == rel.id).all()
        uses = db.query(AuditLog).filter(
            AuditLog.actor_user_id == rel.caregiver_user_id,
            AuditLog.patient_id == p.id).order_by(AuditLog.created_at.desc()).limit(5).all()
        out.append({"relationship_id": rel.id, "caregiver_name": cg_user.name if cg_user else None,
                    "caregiver_phone": cg_user.phone if cg_user else None,
                    "relationship": rel.relationship, "status": rel.status,
                    "permissions": {perm.permission: perm.granted for perm in perms},
                    "recent_access": [{"action": u.action, "at": str(u.created_at),
                                       "result": u.result} for u in uses]})
    return {"caregivers": out}


class InviteBody(BaseModel):
    caregiver_phone: str
    caregiver_name: str
    relationship: str
    permissions: list[str] = []


@app.post("/caregivers/invite", tags=["caregivers"])
def invite_caregiver(body: InviteBody, principal: Principal = Depends(get_current_principal),
                     db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    if principal.role != ROLE_USER:
        raise HTTPException(403, "Only account owners grant caregiver access")
    p = principal.own_patient()
    if not p:
        raise HTTPException(400, "Complete onboarding first")
    phone = body.caregiver_phone.strip()
    if not phone.startswith("+"):
        raise HTTPException(400, "Caregiver phone must include country code, e.g. +91...")
    cg_user = db.query(User).filter(User.phone == phone).first()
    if not cg_user:
        cg_user = User(role=ROLE_CAREGIVER, name=body.caregiver_name[:200], phone=phone,
                       onboarded=False)
        db.add(cg_user)
        db.flush()
    rel = CaregiverRelationship(caregiver_user_id=cg_user.id, patient_id=p.id,
                                relationship=body.relationship[:40], status="PENDING")
    db.add(rel)
    db.flush()
    for perm in body.permissions:
        if perm in CAREGIVER_PERMISSIONS:
            db.add(CaregiverPermission(relationship_id=rel.id, permission=perm, granted=True))
    rel.status = "ACTIVE"  # patient explicitly granted these permissions now
    db.commit()
    audit(db, principal, "PERMISSION_GRANTED", patient_id=p.id,
          record_ref=f"caregiver:{cg_user.id}", purpose=f"relationship={rel.relationship}; "
          f"perms={','.join(body.permissions)}", ip=meta.get("ip"))
    notify(db, cg_user.id, "PERMISSION_GRANTED", "CareRoute access granted",
           f"{principal.user.name} granted you limited access to help with their care.")
    return {"relationship_id": rel.id, "status": rel.status,
            "granted": body.permissions}


class PermissionsBody(BaseModel):
    permissions: list[str]


@app.put("/caregivers/{relationship_id}/permissions", tags=["caregivers"])
def update_caregiver_permissions(relationship_id: int, body: PermissionsBody,
                                 principal: Principal = Depends(get_current_principal),
                                 db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    if principal.role != ROLE_USER:
        raise HTTPException(403, "Only account owners manage caregiver access")
    p = principal.own_patient()
    rel = db.query(CaregiverRelationship).filter(
        CaregiverRelationship.id == relationship_id).first()
    if not rel or not p or rel.patient_id != p.id:
        raise HTTPException(404, "Caregiver relationship not found")
    for perm in CAREGIVER_PERMISSIONS:
        row = db.query(CaregiverPermission).filter(
            CaregiverPermission.relationship_id == rel.id,
            CaregiverPermission.permission == perm).first()
        granted = perm in body.permissions
        if not row:
            db.add(CaregiverPermission(relationship_id=rel.id, permission=perm, granted=granted))
        else:
            row.granted = granted
            row.updated_at = datetime.utcnow()
    db.commit()
    audit(db, principal, "PERMISSION_MODIFIED", patient_id=p.id if p else None,
          record_ref=f"caregiver_rel:{rel.id}", purpose=f"perms={','.join(body.permissions)}",
          ip=meta.get("ip"))
    return {"relationship_id": rel.id, "permissions": body.permissions}


@app.post("/caregivers/{relationship_id}/revoke", tags=["caregivers"])
def revoke_caregiver(relationship_id: int,
                     principal: Principal = Depends(get_current_principal),
                     db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    if principal.role != ROLE_USER:
        raise HTTPException(403, "Only account owners manage caregiver access")
    p = principal.own_patient()
    rel = db.query(CaregiverRelationship).filter(
        CaregiverRelationship.id == relationship_id).first()
    if not rel or not p or rel.patient_id != p.id:
        raise HTTPException(404, "Caregiver relationship not found")
    rel.status = "REVOKED"
    db.commit()
    audit(db, principal, "PERMISSION_REVOKED", patient_id=p.id if p else None,
          record_ref=f"caregiver_rel:{rel.id}", ip=meta.get("ip"))
    notify(db, rel.caregiver_user_id, "PERMISSION_REVOKED", "CareRoute access revoked",
           f"{principal.user.name} revoked your access. Contact them if this was unexpected.")
    return {"revoked": True}


@app.get("/caregivers/my-patients", tags=["caregivers"])
def my_patients(principal: Principal = Depends(require_roles(ROLE_CAREGIVER)),
                db: Session = Depends(get_db)):
    rels = db.query(CaregiverRelationship).filter(
        CaregiverRelationship.caregiver_user_id == principal.id).all()
    out = []
    for rel in rels:
        p = db.get(Patient, rel.patient_id)
        perms = principal.caregiver_permissions(rel.patient_id)
        out.append({"patient_id": rel.patient_id, "name": p.display_name if p else None,
                    "relationship": rel.relationship, "status": rel.status,
                    "permissions": sorted(perms)})
    return {"patients": out}


# ================================================================= PRIVACY
@app.get("/privacy/overview", tags=["privacy"])
def privacy_overview(principal: Principal = Depends(get_current_principal),
                     db: Session = Depends(get_db)):
    if principal.role != ROLE_USER:
        raise HTTPException(403, "The Privacy Center is for CareRoute user accounts")
    p = principal.own_patient()
    if not p:
        return {"caregivers": 0, "note": "Complete onboarding to see access information"}
    caregivers = db.query(CaregiverRelationship).filter(
        CaregiverRelationship.patient_id == p.id, CaregiverRelationship.status == "ACTIVE").count()
    doctors_seen = db.query(AuditLog.actor_user_id).filter(
        AuditLog.patient_id == p.id, AuditLog.actor_role == ROLE_DOCTOR).distinct().count()
    break_glass = db.query(EmergencyAccessEvent).filter(
        EmergencyAccessEvent.patient_id == p.id).order_by(
        EmergencyAccessEvent.requested_at.desc()).limit(5).all()
    history = db.query(AuditLog).filter(AuditLog.patient_id == p.id).order_by(
        AuditLog.created_at.desc()).limit(30).all()
    return {
        "who_has_access": {
            "active_caregivers": caregivers,
            "doctors_with_record_access": doctors_seen,
            "note": "Doctors only see your information when you have an appointment with them, "
                    "and only speciality-relevant information.",
        },
        "break_glass_events": [{"id": e.id, "by_role": "professional", "reason": e.reason,
                                "status": e.status, "requested_at": str(e.requested_at),
                                "justification": e.justification} for e in break_glass],
        "access_history": [{"action": h.action, "role": h.actor_role, "result": h.result,
                            "purpose": h.purpose, "at": str(h.created_at)} for h in history],
    }


# ========================================================= COMMUNITY CARE
@app.get("/community-care/assigned", tags=["community-care"])
def community_assigned(principal: Principal = Depends(require_roles(ROLE_CHW)),
                       db: Session = Depends(get_db)):
    assigns = db.query(CommunityAssignment).filter(
        CommunityAssignment.chw_id == principal.chw.id,
        CommunityAssignment.status == "ACTIVE").all()
    out = []
    for a in assigns:
        p = db.get(Patient, a.patient_id)
        last_log = db.query(HealthLog).filter(HealthLog.patient_id == p.id).order_by(
            HealthLog.logged_at.desc()).first()
        last_visit = db.query(CommunityVisit).filter(
            CommunityVisit.patient_id == p.id).order_by(CommunityVisit.visit_date.desc()).first()
        stamps = [t for t in [last_log.logged_at if last_log else None,
                              datetime.combine(last_visit.visit_date, datetime.min.time())
                              if last_visit and last_visit.visit_date else None] if t]
        last_activity = max(stamps) if stamps else None
        days_quiet = (datetime.utcnow() - last_activity).days if last_activity else None
        # No recent activity is NEVER an automatic medical emergency —
        # it means a wellness follow-up is required (CHW verifies the actual situation).
        wellness_due = days_quiet is None or days_quiet >= 10
        appts = db.query(Appointment).filter(Appointment.patient_id == p.id).order_by(
            Appointment.appointment_date.desc()).limit(3).all()
        out.append({"assignment_id": a.id, "patient_id": p.id, "name": p.display_name,
                    "age": _age(p.date_of_birth), "location_text": p.location_text,
                    "preferred_language": p.preferred_language,
                    "priority": "WELLNESS_DUE" if wellness_due else a.priority,
                    "wellness_follow_up_required": wellness_due,
                    "days_since_last_activity": days_quiet,
                    "note": ("No recent activity — wellness follow-up required. "
                             "Verify the actual situation during a visit.")
                            if wellness_due else "Routine",
                    "recent_appointments": appointment_out_appts(db, appts),
                    "last_visit": str(last_visit.visit_date) if last_visit else None})
    return {"assigned": out}


class VisitBody(BaseModel):
    patient_id: int
    wellness_status: str = "WELL"
    observations: str | None = None
    escalation_flag: bool = False
    follow_up_on: date | None = None


@app.post("/community-care/visit", tags=["community-care"])
def record_visit(body: VisitBody, principal: Principal = Depends(require_roles(ROLE_CHW)),
                 db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    if body.patient_id not in principal.assigned_patient_ids():
        deny(principal, body.patient_id, Access.DEMOGRAPHICS, meta, "CHW visit recording")
    v = CommunityVisit(chw_id=principal.chw.id, patient_id=body.patient_id,
                       visit_date=date.today(), wellness_status=body.wellness_status,
                       observations=body.observations, escalation_flag=body.escalation_flag,
                       follow_up_on=body.follow_up_on)
    db.add(v)
    assign = db.query(CommunityAssignment).filter(
        CommunityAssignment.chw_id == principal.chw.id,
        CommunityAssignment.patient_id == body.patient_id).first()
    if assign:
        assign.priority = "ESCALATED" if body.escalation_flag else "ROUTINE"
    db.commit()
    audit(db, principal, "CHW_VISIT_RECORDED", patient_id=body.patient_id,
          record_ref=f"visit:{v.id}", purpose=body.wellness_status, ip=meta.get("ip"))
    return {"id": v.id, "recorded": True}


@app.get("/community-care/visits", tags=["community-care"])
def community_visits(principal: Principal = Depends(require_roles(ROLE_CHW)),
                     db: Session = Depends(get_db)):
    rows = db.query(CommunityVisit).filter(CommunityVisit.chw_id == principal.chw.id).order_by(
        CommunityVisit.visit_date.desc()).limit(20).all()
    out = []
    for v in rows:
        p = db.get(Patient, v.patient_id)
        out.append({"id": v.id, "patient_name": p.display_name if p else None,
                    "visit_date": str(v.visit_date), "wellness_status": v.wellness_status,
                    "observations": v.observations, "escalation_flag": v.escalation_flag,
                    "follow_up_on": str(v.follow_up_on) if v.follow_up_on else None})
    return {"visits": out}


# =========================================================== MEDICAL CAMPS
@app.get("/medical-camps", tags=["medical-camps"])
def medical_camps(lat: float | None = None, lng: float | None = None, location_text: str | None = None, radius_km: float = 10.0,
                  db: Session = Depends(get_db)):
    """Location-aware camp discovery (§19). Upcoming only, distance-ranked; demo
    listings are clearly labeled. No camps → honest empty state."""
    today = date.today()
    located = lat is not None and lng is not None
    if not located:
        # Medical camps are a nearby-care feature; never return a city-wide/static
        # list when the user location is unavailable.
        return {"camps": [],
                "search": {"lat": lat, "lng": lng, "location_text": location_text, "radius_km": None},
                "nearest_outside_km": None,
                "next_radius_km": None,
                "empty_note": "Enable current location to see nearby medical camps. No location is assumed."}
    out = []
    # Preferred live source: Google Places public place information. It is deliberately
    # a discovery source, not a hospital/EHR integration. Only results whose public
    # name/address actually contains camp-related wording are surfaced.
    active = get_provider(db)
    if isinstance(active, GooglePlacesProvider):
        seen = set()
        for q in ("free medical camp", "medical camp", "health camp"):
            places = active._search_text_general(q, lat, lng, radius_m=max(5000, int(radius_km * 1000))) or []
            for place in places:
                name = (place.get("displayName") or {}).get("text", "").strip()
                address = place.get("formattedAddress", "") or ""
                hay = f"{name} {address}".lower()
                if "camp" not in hay or not name:
                    continue
                loc = place.get("location") or {}
                plat, plng = loc.get("latitude"), loc.get("longitude")
                if plat is None or plng is None:
                    continue
                pid = place.get("id") or f"google:{name}:{plat}:{plng}"
                if pid in seen:
                    continue
                seen.add(pid)
                d = haversine_km(lat, lng, plat, plng)
                if d is not None and d <= radius_km:
                    out.append({"id": pid, "name": name, "camp_date": None,
                                "location_text": address, "latitude": plat, "longitude": plng,
                                "speciality": "Medical / health camp",
                                "services": "Public place listing — verify services and date before attending.",
                                "organizer": "Public listing",
                                "registration": None,
                                "contact": place.get("internationalPhoneNumber", ""),
                                "verified_source": "GOOGLE_PLACES_PUBLIC",
                                "distance_km": d, "_demo": False})

    # Controlled prototype listings remain useful for the academic demo when no live
    # camp source is configured. They are always date- and location-filtered.
    if not out:
        rows = db.query(MedicalCamp).filter(MedicalCamp.camp_date >= today).order_by(
            MedicalCamp.camp_date.asc()).all()
        for c in rows:
            d = haversine_km(lat, lng, c.latitude, c.longitude)
            if d is not None and d <= radius_km:
                out.append({"id": c.id, "name": c.name, "camp_date": str(c.camp_date),
                            "location_text": c.location_text, "latitude": c.latitude,
                            "longitude": c.longitude, "speciality": c.speciality,
                            "services": c.services, "organizer": c.organizer,
                            "registration": c.registration, "contact": c.contact,
                            "verified_source": c.verified_source,
                            "distance_km": d,
                            "_demo": ("DEMO" in (c.verified_source or "").upper())})

    out.sort(key=lambda c: (c["distance_km"] if c["distance_km"] is not None else 1e9,
                            c.get("camp_date") or "9999-99-99"))
    next_radius = next((r for r in (5, 10, 25, 100) if r > radius_km), None) if located else None
    return {"camps": out,
            "search": {"lat": lat, "lng": lng, "location_text": location_text, "radius_km": radius_km if located else None},
            "nearest_outside_km": None,
            "next_radius_km": next_radius,
            "empty_note": ("No verified medical camps found nearby for this radius. Live public listings "
                           "are searched when configured; otherwise only future controlled demo listings "
                           "are shown. None are invented." if located
                           else "Enable current location to see nearby medical camps. None are invented.")}


# ============================================================== EMERGENCY
def _emergency_summary(db: Session, p: Patient, situation: str | None) -> dict:
    """Minimum-necessary Emergency Health Summary. Built server-side from authorized data."""
    allergies = db.query(Allergy).filter(Allergy.patient_id == p.id).all()
    critical_conditions = db.query(MedicalCondition).filter(
        MedicalCondition.patient_id == p.id,
        MedicalCondition.status.in_(["ACTIVE", "MANAGED"])).all()
    meds = db.query(Medication).filter(Medication.patient_id == p.id,
                                       Medication.status == "ACTIVE").all()
    return {
        "name": p.display_name, "blood_group": p.blood_group,
        "location_text": p.location_text, "latitude": p.latitude, "longitude": p.longitude,
        "emergency_contact": (f"{p.emergency_contact_name} ({p.emergency_contact_relation})"
                              if p.emergency_contact_name else None),
        "emergency_phone": p.emergency_contact_phone,
        "allergies": [{"allergen": a.allergen, "severity": a.severity} for a in allergies],
        "critical_conditions": [c.condition for c in critical_conditions],
        "important_medications": [m.name for m in meds][:8],
        "situation_reported_by_user": situation,
        "prepared_at": datetime.utcnow().isoformat(),
        "data_basis": "CareRoute authorized emergency profile — minimum necessary information",
    }


@app.post("/emergency/trigger", tags=["emergency"])
def emergency_trigger(body: dict, principal: Principal = Depends(get_current_principal),
                      db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    """Manual emergency activation. Works regardless of daily health log usage."""
    situation = str(body.get("situation", ""))[:500]
    lat, lng = body.get("latitude"), body.get("longitude")
    if principal.role == ROLE_USER:
        p = principal.own_patient()
        if not p:
            raise HTTPException(400, "Complete onboarding first")
    elif principal.role == ROLE_CAREGIVER:
        pid = body.get("patient_id")
        if not pid:
            raise HTTPException(400, "patient_id required")
        p = patient_for_check(db, int(pid))
        if "emergency_assist" not in principal.caregiver_permissions(p.id):
            deny(principal, p.id, Access.DEMOGRAPHICS, meta, "caregiver emergency assist")
    elif principal.role == ROLE_CHW:
        pid = body.get("patient_id")
        if not pid or pid not in principal.assigned_patient_ids():
            raise HTTPException(403, "Not an assigned user")
        p = db.get(Patient, pid)
        caregiver_flag = False
    else:
        raise HTTPException(403, "Emergency activation is for users, caregivers and CHWs")
    # Emergency facility routing requires a CURRENT device location. Stored profile
    # location may be included in the health summary, but is never silently used
    # as the destination-search origin.
    if lat is not None and lng is not None:
        p.latitude, p.longitude = lat, lng
        p.location_text = body.get("location_text") or p.location_text
    summary = _emergency_summary(db, p, situation or None)
    # Current device location ONLY: if none was captured, no destination search is
    # attempted and the event keeps whatever location is on file for the summary.
    eff_lat = lat
    eff_lng = lng
    # Emergency-capable facilities via the SAME real location pipeline (§18).
    # Prioritize emergency-capable hospitals — not simply the nearest clinic.
    # IMPORTANT: the (slow) live provider search runs BEFORE the EmergencyEvent
    # INSERT so the write transaction never spans a network call — concurrent
    # role dashboards polling /sync must never hit "database is locked".
    capable: list[dict] = []
    facilities_note: str | None = None
    if eff_lat is not None and eff_lng is not None:
        active = get_provider(db)
        if isinstance(active, OverpassProvider):
            out = active.search_nearby_hospitals(
                eff_lat, eff_lng, 15000, filters={"emergency": True, "limit": 25})
            if out["status"] == "ok":
                for r in out["results"]:
                    capable.append({"hospital_id": r.get("osm_id"), "name": r["name"],
                                    "address": r.get("address") or "Address unavailable",
                                    "phone": r.get("phone") or "",
                                    "latitude": r["latitude"], "longitude": r["longitude"],
                                    "distance_km": haversine_km(eff_lat, eff_lng,
                                                                r["latitude"], r["longitude"]),
                                    "emergency_phone_verified": bool(r.get("phone")),
                                    "data_source": "OPENSTREETMAP_OVERPASS"})
                capable.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 1e9)
                # §18: prefer genuine hospitals with a contactable line over unmapped ones.
                hospitals_first = [c for c in capable if c["phone"]] or capable
                capable = hospitals_first
            else:
                facilities_note = ("Live emergency facility search is temporarily unavailable "
                                   "— call 108 directly. Navigation to a specific facility can "
                                   "be retried from the Hospitals page.")
        elif isinstance(active, GooglePlacesProvider):
            places = active._search_nearby(eff_lat, eff_lng, radius_m=15000)
            if places:
                for p in places:
                    r = GooglePlacesProvider._place_to_hospital(p)
                    capable.append({"hospital_id": None, "name": r["name"],
                                    "address": r.get("address") or "Address unavailable",
                                    "phone": r.get("phone") or "",
                                    "latitude": r["latitude"], "longitude": r["longitude"],
                                    "distance_km": haversine_km(eff_lat, eff_lng,
                                                                r["latitude"], r["longitude"]),
                                    "emergency_phone_verified": bool(r.get("phone")),
                                    "data_source": "GOOGLE_PLACES_LIVE"})
                capable.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 1e9)
    if eff_lat is None or eff_lng is None:
        facilities_note = ("Current location was not captured, so CareRoute did not guess a "
                           "nearby facility. Call 108 directly and enable location to see "
                           "nearby routing options.")
    capable.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 1e9)
    ev = EmergencyEvent(patient_id=p.id, triggered_by_user_id=principal.id,
                        latitude=eff_lat, longitude=eff_lng,
                        location_text=summary["location_text"], situation=situation or None,
                        summary=summary)
    db.add(ev)
    db.flush()
    ev.facility_hospital_id = capable[0]["hospital_id"] if capable else None
    # Notify emergency contacts' registered users + primary user.
    if p.user_id:
        notify(db, p.user_id, "EMERGENCY_EVENT", "Emergency activated",
               "Emergency assistance was activated for your record.", ev.id)
    audit(db, principal, "EMERGENCY_TRIGGERED", patient_id=p.id, record_ref=f"emergency:{ev.id}",
          purpose=situation or "manual activation", ip=meta.get("ip"), device=meta.get("device"))
    db.commit()
    db.refresh(ev)
    return {"event_id": ev.id, "summary": summary, "facilities": capable[:3],
            **({"facilities_note": facilities_note} if facilities_note else {}),
            "ambulance_status": {"available": False, "state": "LIVE_UNAVAILABLE",
                                 "message": "Ambulance live status unavailable — no official "
                                            "emergency-services integration in this prototype."},
            "voice_script_pending": True}


def _emergency_actor_patient_id(principal: Principal, db: Session) -> int | None:
    """The patient an emergency actor acts for: self for users, cared-for patient for
    caregivers (resolved through their ACTIVE authorized relationship)."""
    if principal.role == ROLE_USER:
        p = principal.own_patient()
        return p.id if p else None
    if principal.role == ROLE_CAREGIVER:
        rel = db.query(CaregiverRelationship).filter(
            CaregiverRelationship.caregiver_user_id == principal.id,
            CaregiverRelationship.status == "ACTIVE").first()
        return rel.patient_id if rel else None
    return None


@app.get("/emergency/{event_id}/voice-script", tags=["emergency"])
def emergency_voice_script(event_id: int,
                           principal: Principal = Depends(get_current_principal),
                           db: Session = Depends(get_db)):
    ev = db.get(EmergencyEvent, event_id)
    if not ev:
        raise HTTPException(404, "Emergency event not found")
    if principal.role in (ROLE_USER, ROLE_CAREGIVER):
        pid = _emergency_actor_patient_id(principal, db)
        if pid is None or pid != ev.patient_id:
            raise HTTPException(403, "Not your emergency event")
    elif principal.role == ROLE_CHW:
        if ev.patient_id not in principal.assigned_patient_ids():
            raise HTTPException(403, "Not an assigned user")
    else:
        raise HTTPException(403, "Not authorized")
    result = ai_service.prepare_emergency_voice_script(ev.summary or {})
    if not ev.voice_script:
        ev.voice_script = result["voice_script"]
        db.commit()
    return {"event_id": ev.id, "voice_script": result["voice_script"], "engine": result["engine"],
            "note": "Prototype voice workflow. No official 108 integration — integration point "
                    "reserved for future authorized emergency services connection."}


@app.post("/emergency/{event_id}/resolve", tags=["emergency"])
def emergency_resolve(event_id: int, principal: Principal = Depends(get_current_principal),
                      db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    ev = db.get(EmergencyEvent, event_id)
    if not ev:
        raise HTTPException(404, "Emergency event not found")
    if principal.role in (ROLE_USER, ROLE_CAREGIVER):
        pid = _emergency_actor_patient_id(principal, db)
        if pid is None or pid != ev.patient_id:
            raise HTTPException(403, "Not your emergency event")
    elif principal.role == ROLE_CHW:
        if ev.patient_id not in principal.assigned_patient_ids():
            raise HTTPException(403, "Not an assigned user")
    else:
        raise HTTPException(403, "Not authorized")
    ev.status = "RESOLVED"
    ev.resolved_at = datetime.utcnow()
    db.commit()
    audit(db, principal, "EMERGENCY_RESOLVED", patient_id=ev.patient_id,
          record_ref=f"emergency:{ev.id}", ip=meta.get("ip"))
    return {"resolved": True}


# NOTE: the emergency QR feature was REMOVED by design decision (§26): the finalized
# CareRoute emergency flow is Confirm → live location → summary → CALL 108 → voice
# briefing → live nearby emergency facilities → navigation. No QR card exists.


# ==================================================== BREAK-GLASS ACCESS
class BreakGlassBody(BaseModel):
    patient_id: int
    reason: str = Field(min_length=10)


# ==================================================== BREAK-GLASS ACCESS
class BreakGlassBody(BaseModel):
    patient_id: int
    reason: str = Field(min_length=10)


@app.post("/emergency-access/invoke", tags=["emergency-access"])
def invoke_break_glass(body: BreakGlassBody,
                       principal: Principal = Depends(require_roles(ROLE_DOCTOR, ROLE_STAFF)),
                       db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    patient_for_check(db, body.patient_id)
    ev = principal.invoke_break_glass(body.patient_id, body.reason.strip())
    audit(db, principal, "EMERGENCY_ACCESS", patient_id=body.patient_id,
          record_ref=f"break_glass:{ev.id}", purpose=body.reason,
          detail=f"expires {ev.expires_at}", ip=meta.get("ip"))
    if db.get(Patient, body.patient_id).user_id:
        notify(db, db.get(Patient, body.patient_id).user_id,
               "EMERGENCY_ACCESS", "Emergency access recorded",
               "A healthcare professional used break-glass emergency access to your record. "
               "This is visible in your Privacy Center access history.")
    return {"break_glass_id": ev.id, "expires_at": str(ev.expires_at),
            "justification_due": str(ev.justification_due),
            "scope": "Time-boxed emergency access. Post-event justification required. "
                     "All access is audited and visible to the patient."}


@app.post("/emergency-access/{event_id}/justify", tags=["emergency-access"])
def justify_break_glass(event_id: int, body: dict,
                        principal: Principal = Depends(require_roles(ROLE_DOCTOR, ROLE_STAFF)),
                        db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    ev = db.query(EmergencyAccessEvent).filter(
        EmergencyAccessEvent.id == event_id,
        EmergencyAccessEvent.actor_user_id == principal.id).first()
    if not ev:
        raise HTTPException(404, "Break-glass event not found")
    ev.justification = str(body.get("justification", ""))[:1000]
    ev.status = "JUSTIFIED"
    db.commit()
    audit(db, principal, "BREAK_GLASS_JUSTIFY", patient_id=ev.patient_id,
          record_ref=f"break_glass:{ev.id}", purpose=ev.justification, ip=meta.get("ip"))
    return {"justified": True}


# =========================================================== NOTIFICATIONS
@app.get("/notifications", tags=["notifications"])
def list_notifications(principal: Principal = Depends(get_current_principal),
                       db: Session = Depends(get_db)):
    rows = db.query(Notification).filter(Notification.user_id == principal.id).order_by(
        Notification.created_at.desc()).limit(50).all()
    return {"notifications": [{"id": n.id, "type": n.type, "title": n.title, "body": n.body,
                               "read": n.read, "created_at": str(n.created_at)} for n in rows],
            "unread": sum(1 for n in rows if not n.read)}


@app.post("/notifications/{notification_id}/read", tags=["notifications"])
def read_notification(notification_id: int, principal: Principal = Depends(get_current_principal),
                      db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == notification_id,
                                      Notification.user_id == principal.id).first()
    if not n:
        raise HTTPException(404, "Notification not found")
    n.read = True
    db.commit()
    return {"read": True}


@app.post("/notifications/read-all", tags=["notifications"])
def read_all_notifications(principal: Principal = Depends(get_current_principal),
                           db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.user_id == principal.id,
                                  Notification.read == False).update({"read": True})  # noqa: E712
    db.commit()
    return {"read": True}


# =================================================================== LIVE SYNC
# The four-laptop demonstration (§35) requires genuine multi-role synchronization:
# "receptionist IMMEDIATELY sees the new request", "user receives confirmation".
# Lightweight polling (3s) against this token endpoint keeps every open dashboard
# current; heavy lists are re-fetched only when the token changes.
SYNC_HINT_SECONDS = 3


@app.get("/sync", tags=["system"])
def sync_token(principal: Principal = Depends(get_current_principal),
               db: Session = Depends(get_db)):
    """Per-user liveness token: changes whenever anything new happens for this user
    (new notification, changed appointment, new prescription). Clients poll this
    cheap endpoint and reload their dashboard data only when it moves."""
    row = db.query(Notification.sync_token).filter(
        Notification.user_id == principal.id).order_by(
        Notification.id.desc()).limit(1).first()
    latest_appt = db.query(Appointment.updated_at).filter(
        _appointment_scope_filter(db, principal)).order_by(
        Appointment.updated_at.desc()).limit(1).scalar()
    return {"sync_token": (row[0] if row and row[0] else None)
            or (f"appt:{latest_appt}" if latest_appt else "none"),
            "poll_after_seconds": SYNC_HINT_SECONDS,
            "server_time": str(datetime.utcnow())}


def _appointment_scope_filter(db: Session, principal: Principal):
    """SQLAlchemy filter limiting appointments to what this principal may see."""
    q = db.query(Appointment.id)
    if principal.role == ROLE_USER:
        p = principal.own_patient()
        return q.filter(Appointment.patient_id == p.id) if p else q.filter(Appointment.id == -1)
    if principal.role == ROLE_CAREGIVER:
        ids = [pid for pid, perms in my_patients_rows(db, principal)
               if "view_appointments" in perms]
        return q.filter(Appointment.patient_id.in_(ids or [-1]))
    if principal.role == ROLE_DOCTOR:
        return q.filter(Appointment.doctor_id == principal.doctor.id) if principal.doctor \
            else q.filter(Appointment.id == -1)
    if principal.role == ROLE_STAFF:
        return q.filter(Appointment.hospital_id == principal.staff_hospital_id)
    if principal.role == ROLE_ADMIN:
        return q.filter(Appointment.hospital_id == principal.admin_hospital_id)
    if principal.role == ROLE_CHW:
        ids = principal.assigned_patient_ids()
        return q.filter(Appointment.patient_id.in_(ids or [-1]))
    return q.filter(Appointment.id == -1)


# =================================================================== AUDIT
@app.get("/audit", tags=["audit"])
def view_audit(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    """Role-scoped audit visibility: users see access to their own record;
    doctor/staff/admin see events for their hospital context."""
    q = db.query(AuditLog)
    if principal.role in (ROLE_USER, ROLE_CAREGIVER):
        p = principal.own_patient()
        q = q.filter(AuditLog.patient_id == p.id) if p else q.filter(AuditLog.id == -1)
    elif principal.role == ROLE_DOCTOR:
        q = q.filter(AuditLog.actor_user_id == principal.id)
    elif principal.role in (ROLE_STAFF, ROLE_ADMIN):
        hosp = principal.staff_hospital_id or principal.admin_hospital_id
        q = q.filter(AuditLog.hospital_id == hosp)
    else:
        q = q.filter(AuditLog.actor_user_id == principal.id)
    rows = q.order_by(AuditLog.created_at.desc()).limit(100).all()
    return {"audit": [{"id": a.id, "action": a.action, "actor_role": a.actor_role,
                       "result": a.result, "purpose": a.purpose, "record_ref": a.record_ref,
                       "detail": a.detail, "at": str(a.created_at)} for a in rows]}


# =================================================================== ADMIN
@app.get("/admin/overview", tags=["admin"])
def admin_overview(principal: Principal = Depends(require_roles(ROLE_ADMIN)),
                   db: Session = Depends(get_db)):
    h = db.get(Hospital, principal.admin_hospital_id)
    departments = db.query(HospitalDepartment).filter(HospitalDepartment.hospital_id == h.id).all()
    doctors = db.query(DoctorHospitalAffiliation, Doctor).join(
        Doctor, DoctorHospitalAffiliation.doctor_id == Doctor.id).filter(
        DoctorHospitalAffiliation.hospital_id == h.id).all()
    staff = db.query(HospitalStaff).filter(HospitalStaff.hospital_id == h.id).all()
    appt_stats = {}
    for status in ("REQUESTED", "CONFIRMED", "COMPLETED", "REJECTED", "RESCHEDULED"):
        appt_stats[status] = db.query(Appointment).filter(
            Appointment.hospital_id == h.id, Appointment.status == status).count()
    return {"hospital": {"id": h.id, "name": h.name, "type": h.hospital_type,
                         "address": h.address, "city": h.city, "phone": h.phone,
                         "emergency_phone": h.emergency_phone, "website": h.website,
                         "data_source": h.data_source},
            "departments": [{"id": d.id, "name": d.name, "speciality_key": d.speciality_key}
                            for d in departments],
            "doctors": [{"doctor_id": d.id, "name": d.name, "qualification": d.qualification,
                         "speciality_key": d.speciality_key, "verification": d.verification_status}
                        for _, d in doctors],
            "staff": [{"staff_id": s.id, "user_id": s.user_id, "designation": s.designation,
                       "department": s.department} for s in staff],
            "appointment_stats": appt_stats}


class DepartmentIn(BaseModel):
    name: str
    speciality_key: str


@app.post("/admin/departments", tags=["admin"])
def admin_add_department(body: DepartmentIn,
                         principal: Principal = Depends(require_roles(ROLE_ADMIN)),
                         db: Session = Depends(get_db)):
    d = HospitalDepartment(hospital_id=principal.admin_hospital_id, name=body.name[:120],
                           speciality_key=body.speciality_key[:48])
    db.add(d)
    db.commit()
    return {"id": d.id}


class StaffIn(BaseModel):
    name: str
    designation: str
    department: str


@app.post("/admin/staff", tags=["admin"])
def admin_add_staff(body: StaffIn, principal: Principal = Depends(require_roles(ROLE_ADMIN)),
                    db: Session = Depends(get_db)):
    """Creates an authorized staff account. MFA (OTP) is mandatory at first login."""
    existing = db.query(User).filter(User.name == body.name, User.role == ROLE_STAFF).first()
    if existing:
        raise HTTPException(409, "Staff member already exists")
    next_id = db.query(HospitalStaff).count() + 201
    u = User(role=ROLE_STAFF, name=body.name[:200],
             worker_id=f"STF{next_id:03d}", password_hash=None, mfa_enabled=True)
    db.add(u)
    db.flush()
    db.add(HospitalStaff(user_id=u.id, hospital_id=principal.admin_hospital_id,
                         designation=body.designation[:80], department=body.department[:120]))
    db.commit()
    return {"user_id": u.id, "worker_id": u.worker_id,
            "note": "Share the Staff ID with the staff member. Login uses phone-free OTP: "
                    "request OTP with this ID; first login requires no password (OTP is the credential)."}


@app.get("/admin/data-sources", tags=["admin"])
def admin_data_sources(principal: Principal = Depends(require_roles(ROLE_ADMIN)),
                       db: Session = Depends(get_db)):
    rows = db.query(DataSource).all()
    provider = get_provider(db)
    return {"data_sources": [{"id": r.id, "name": r.name, "provider_type": r.provider_type,
                              "status": r.status, "scope": r.scope,
                              "last_synced_at": str(r.last_synced_at) if r.last_synced_at else None,
                              "config": r.config} for r in rows],
            "active_provider": provider.integration_status()}


# ==================================================================== FHIR
@app.get("/fhir/mapping", tags=["fhir"])
def fhir_mapping():
    """Conceptual FHIR-readiness boundary. NOT a FHIR server — a mapping contract."""
    from fhir import FHIR_RESOURCE_MAP
    return {"fhir_version_target": "R4", "server_mode": False,
            "conceptual_map": FHIR_RESOURCE_MAP,
            "note": "Internal entities carry stable keys so a future authorized "
                    "integration can translate to FHIR resources without redesign."}


@app.get("/fhir/Patient/{patient_id}", tags=["fhir"])
def fhir_patient(patient_id: int, principal: Principal = Depends(get_current_principal),
                 db: Session = Depends(get_db), meta: dict = Depends(get_request_meta)):
    _patient_access_or_denied(principal, patient_id, Access.DEMOGRAPHICS, meta,
                              "FHIR conceptual export")
    p = db.get(Patient, patient_id)
    return {"resourceType": "Patient (conceptual mapping — not a FHIR server)",
            "id": p.id, "name": [{"text": p.display_name}],
            "birthDate": str(p.date_of_birth) if p.date_of_birth else None,
            "extension": {"blood_group": p.blood_group, "preferred_language": p.preferred_language}}


# ============================================================== SYSTEM
@app.get("/system/provider-status", tags=["system"])
def provider_status(db: Session = Depends(get_db)):
    return {"provider": get_provider(db).integration_status(),
            "environment": settings.ENVIRONMENT,
            "ai_engine": "server_side_llm" if ai_service.AI_API_KEY else "deterministic_summarizer",
            "tagline": settings.TAGLINE}


@app.get("/healthz", tags=["system"])
def healthz(db: Session = Depends(get_db)):
    db.query(Hospital).count()
    return {"status": "ok", "app": settings.APP_NAME}


@app.on_event("startup")
def startup():
    from database import engine, SessionLocal
    from models import Base
    Base.metadata.create_all(engine)
    # Lightweight column migrations for pre-existing prototype databases.
    import sqlalchemy
    insp = sqlalchemy.inspect(engine)
    with engine.connect() as conn:
        if "sync_token" not in [c["name"] for c in insp.get_columns("notifications")]:
            conn.execute(sqlalchemy.text(
                "ALTER TABLE notifications ADD COLUMN sync_token VARCHAR(64)"))
        if "last_taken_on" not in [c["name"] for c in insp.get_columns("medications")]:
            conn.execute(sqlalchemy.text(
                "ALTER TABLE medications ADD COLUMN last_taken_on DATE"))
        conn.commit()
    db = SessionLocal()
    try:
        if db.query(Hospital).count() == 0:
            import seed as seed_mod
            seed_mod.seed()
    finally:
        db.close()


# Serve the built frontend (single-port deployment). Client-side routes fall back
# to index.html; real asset paths are served directly (with traversal protection).
import os
FRONTEND_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if os.path.isdir(FRONTEND_DIST):
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        target = os.path.abspath(os.path.join(FRONTEND_DIST, full_path))
        if target.startswith(FRONTEND_DIST) and os.path.isfile(target):
            return FileResponse(target)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
