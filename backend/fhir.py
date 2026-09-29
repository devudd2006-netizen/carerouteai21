"""CareRoute AI — FHIR-ready conceptual mapping layer.

The prototype does NOT run a FHIR server. Internal entities carry stable keys that
map conceptually to FHIR resources so a future authorized integration (HL7 FHIR R4)
can translate without redesign:

    Patient            -> patients / users(user role USER)
    Practitioner       -> doctors
    Organization       -> hospitals
    Condition          -> medical_conditions
    Observation        -> health_logs / community visits observations
    MedicationRequest  -> prescriptions (+ prescription_items, medications)
    DiagnosticReport   -> medical_reports (type LAB / IMAGING)
    DocumentReference  -> medical_reports (type DOCUMENT)
    Encounter          -> appointments (status COMPLETED)
    Appointment        -> appointments
    CarePlan           -> caregiver_permissions + community assignments
"""
from config import settings

FHIR_RESOURCE_MAP = {
    "Patient": ["patients", "user_profiles"],
    "Practitioner": ["doctors"],
    "Organization": ["hospitals", "hospital_departments"],
    "Condition": ["medical_conditions"],
    "Observation": ["health_logs"],
    "MedicationRequest": ["prescriptions", "prescription_items", "medications"],
    "DiagnosticReport": ["medical_reports(report_type in LAB,IMAGING)"],
    "DocumentReference": ["medical_reports(report_type=DOCUMENT)"],
    "Encounter": ["appointments(status=COMPLETED)"],
    "Appointment": ["appointments"],
    "CarePlan": ["caregiver_permissions", "community_assignments"],
}

SPECIALITIES = {
    "orthopaedics": {"label": "Orthopaedics", "fhirspecialty": "http://snomed.info/sct|24136001"},
    "cardiology": {"label": "Cardiology", "fhirspecialty": "http://snomed.info/sct|34481000"},
    "oncology": {"label": "Oncology", "fhirspecialty": "http://snomed.info/sct|394914008"},
    "ophthalmology": {"label": "Ophthalmology", "fhirspecialty": "http://snomed.info/sct|394594003"},
    "urology": {"label": "Urology", "fhirspecialty": "http://snomed.info/sct|394649004"},
    "general_medicine": {"label": "General Medicine", "fhirspecialty": "http://snomed.info/sct|394802001"},
    "ent": {"label": "ENT", "fhirspecialty": "http://snomed.info/sct|394977005"},
    "dermatology": {"label": "Dermatology", "fhirspecialty": "http://snomed.info/sct|394582002"},
    "obstetrics_gynaecology": {"label": "Obstetrics & Gynaecology", "fhirspecialty": "http://snomed.info/sct|394915009"},
    "emergency": {"label": "Emergency Medicine", "fhirspecialty": "http://snomed.info/sct|77343006"},
}

CONCERN_TO_SPECIALITY = [
    # (keywords, speciality) — heuristic care navigation, explicitly NOT diagnosis
    (("bone", "joint", "fracture", "knee", "back pain", "shoulder", "hip", "sprain"), "orthopaedics"),
    (("heart", "chest pain", "palpitation", "bp", "blood pressure"), "cardiology"),
    (("cancer", "tumor", "tumour", "lump", "chemotherapy"), "oncology"),
    (("eye", "vision", "blurred", "cataract", "spectacles"), "ophthalmology"),
    (("urine", "urinary", "kidney", "stone", "urination"), "urology"),
    (("ear", "throat", "nose", "hearing", "sinus", "tonsil"), "ent"),
    (("skin", "rash", "itching", "acne"), "dermatology"),
    (("pregnan", "periods", "menstrual", "gynae"), "obstetrics_gynaecology"),
]


def suggest_speciality(concern: str) -> list[dict]:
    """Heuristic triage aid. Returns suggested specialities; never a diagnosis."""
    text = (concern or "").lower()
    scored = []
    for keywords, key in CONCERN_TO_SPECIALITY:
        matches = [kw for kw in keywords if kw in text]
        if matches:
            meta = SPECIALITIES.get(key, {})
            scored.append({"speciality_key": key, "label": meta.get("label", key),
                           "matched_on": matches, "is_diagnosis": False})
    return scored
