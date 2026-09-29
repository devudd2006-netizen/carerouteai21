"""CareRoute AI — controlled demonstration dataset.

Publicly verified hospital information (address / phone / coordinates from official
or public directory sources). All clinical records, staff, doctors and patients are
SYNTHETIC demonstration identities — no real private patient data, no invented
credentials for real people, no fabricated live operational data.
"""
from datetime import date, datetime, timedelta

from database import Base, SessionLocal, engine
from models import (
    Allergy, Appointment, AuditLog, CaregiverPermission, CaregiverRelationship,
    CommunityAssignment, CommunityHealthWorker, CommunityVisit, DataSource, DeviceCredential,
    Doctor, DoctorHospitalAffiliation, EmergencyContact, EmergencyEvent, HealthLog,
    Hospital, HospitalAdmin, HospitalDepartment, HospitalFacility, HospitalStaff,
    MedicalCamp, MedicalCondition, MedicalReport, Medication, Notification, OtpCode,
    Patient, Prescription, PrescriptionItem, UserProfile, User,
)
from security import hash_password, hash_token, create_refresh_token
from fhir import SPECIALITIES

# ----------------------------------------------------------------- hospitals
# Publicly verified identity information (official district directory / hospital website).
HOSPITALS = [
    {
        "name": "Rajiv Gandhi Government General Hospital",
        "hospital_type": "Government",
        "address": "Poonamallee High Road, Park Town",
        "city": "Chennai", "pincode": "600003",
        "latitude": 13.0806, "longitude": 80.2751,
        "phone": "044-25305000", "emergency_phone": "044-25305711",
        "website": "https://www.mmc.tn.gov.in",
        "description": "Large government teaching hospital attached to Madras Medical College, "
                       "serving Chennai with multi-speciality care and 24x7 emergency services.",
        "verified_fields": {"name": True, "address": True, "phone": True,
                            "emergency_phone": True, "location": True},
    },
    {
        "name": "Apollo Hospitals Greams Road",
        "hospital_type": "Private",
        "address": "21, Greams Lane, Off Greams Road, Thousand Lights",
        "city": "Chennai", "pincode": "600006",
        "latitude": 13.0637, "longitude": 80.2523,
        "phone": "044-40401066", "emergency_phone": "1066",
        "website": "https://www.apollohospitals.com/hospitals/apollo-hospitals-greams-road-chennai",
        "description": "Flagship private multi-speciality hospital of the Apollo group in Chennai.",
        "verified_fields": {"name": True, "address": True, "phone": True,
                            "location": True, "website": True},
    },
    {
        "name": "Cancer Institute (WIA), Adyar",
        "hospital_type": "Non-profit",
        "address": "No. 38, Sardar Patel Road, Adyar",
        "city": "Chennai", "pincode": "600036",
        "latitude": 13.0067, "longitude": 80.2508,
        "phone": "044-22209150", "emergency_phone": "044-22209150",
        "website": "https://cancerinstitutewia.in",
        "description": "Non-profit comprehensive cancer care and research centre founded in 1954.",
        "verified_fields": {"name": True, "address": True, "phone": True,
                            "location": True, "website": True},
    },
]

# Departments per hospital (publicly listed specialities).
DEPARTMENTS = {
    1: [("Orthopaedics", "orthopaedics"), ("Cardiology", "cardiology"),
        ("General Medicine", "general_medicine"), ("Ophthalmology", "ophthalmology"),
        ("Emergency & Trauma", "emergency")],
    2: [("Orthopaedics", "orthopaedics"), ("Cardiology", "cardiology"),
        ("Urology", "urology"), ("ENT", "ent"), ("Dermatology", "dermatology"),
        ("Emergency Care", "emergency")],
    3: [("Medical Oncology", "oncology"), ("Surgical Oncology", "oncology"),
        ("Radiation Oncology", "oncology"), ("Palliative Care", "general_medicine")],
}

FACILITIES = {
    1: [("24x7 Emergency & Casualty", "emergency", True), ("Blood Bank", "support", True),
        ("Pharmacy", "pharmacy", True), ("Radiology / Imaging", "diagnostics", True),
        ("Laboratory", "diagnostics", True)],
    2: [("24x7 Emergency", "emergency", True), ("ICU", "critical_care", True),
        ("Pharmacy", "pharmacy", True), ("Laboratory", "diagnostics", True),
        ("Ambulance Service", "transport", True)],
    3: [("Day Care Chemotherapy", "oncology_support", True), ("Laboratory", "diagnostics", True),
        ("Radiology", "diagnostics", True), ("Pharmacy", "pharmacy", True)],
}

# Controlled demonstration doctor identities — clearly labeled demo profiles.
DOCTORS = [
    # (key, name, qualification, speciality, designation, exp, hospital_idx, dept_idx, opd)
    ("Dr. Aravind Kumar", "MBBS, MS (Orthopaedics)", "orthopaedics", "Orthopaedic Surgeon", 14, 1, 0,
     "Mon–Fri", "09:00–13:00"),
    ("Dr. Priya Venkatesan", "MBBS, MD (General Medicine)", "general_medicine", "Physician", 9, 1, 2,
     "Mon–Sat", "10:00–14:00"),
    ("Dr. Suresh Balaji", "MBBS, MD, DM (Cardiology)", "cardiology", "Interventional Cardiologist", 17, 1, 1,
     "Tue–Sat", "08:00–12:00"),
    ("Dr. Meera Raghavan", "MBBS, MS (Orthopaedics)", "orthopaedics", "Joint Replacement Surgeon", 11, 2, 0,
     "Mon–Fri", "14:00–18:00"),
    ("Dr. Karthik Srinivasan", "MBBS, MD, DM (Cardiology)", "cardiology", "Cardiologist", 8, 2, 1,
     "Mon–Fri", "10:00–13:00"),
    ("Dr. Lakshmi Narayanan", "MBBS, MD, DM (Medical Oncology)", "oncology", "Medical Oncologist", 19, 3, 0,
     "Mon–Thu", "09:00–12:00"),
    ("Dr. Anand Rajagopal", "MBBS, MS, MCh (Surgical Oncology)", "oncology", "Surgical Oncologist", 13, 3, 1,
     "Mon–Fri", "10:00–13:00"),
]

STAFF = [
    ("Latha Mahadevan", 1, "Receptionist", "OPD Front Desk"),
    ("Gopal Krishnan", 2, "Receptionist", "OPD Front Desk"),
    ("Rekha Iyer", 3, "OPD Coordinator", "Patient Services"),
]

PW = "CareRoute@2026"


def _date(d: date, days: int) -> date:
    return d + timedelta(days=days)


def seed():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    today = date.today()
    pw_hash = hash_password(PW)
    refresh = hash_token(create_refresh_token())

    # ------------------------------------------------------------ hospitals
    hospitals = []
    for spec in HOSPITALS:
        h = Hospital(**spec, data_source="VERIFIED_STATIC")
        db.add(h)
        db.flush()
        hospitals.append(h)
        for dname, dkey in DEPARTMENTS[len(hospitals)]:
            db.add(HospitalDepartment(hospital_id=h.id, name=dname, speciality_key=dkey,
                                      description=f"{dname} department"))
        for fname, fcat, verified in FACILITIES[len(hospitals)]:
            db.add(HospitalFacility(hospital_id=h.id, name=fname, category=fcat, verified=verified))
    db.flush()

    # ---------------------------------------------------------- demo users
    users, doctors = {}, {}
    for name, qual, skey, desig, exp, hidx, didx, opd_days, hours in DOCTORS:
        u = User(role="DOCTOR", name=name, worker_id=f"DOC{len(doctors)+101:03d}",
                 password_hash=pw_hash)
        db.add(u)
        db.flush()
        users[name] = u
        doc = Doctor(user_id=u.id, name=name, qualification=qual, speciality_key=skey,
                     designation=desig, years_experience=exp,
                     verification_status="DEMO_IDENTITY",
                     profile_note="Controlled demonstration identity for the CareRoute prototype. "
                                  "Not a listing of a real practitioner.")
        db.add(doc)
        db.flush()
        dept = db.query(HospitalDepartment).filter(
            HospitalDepartment.hospital_id == hospitals[hidx - 1].id,
            HospitalDepartment.speciality_key == skey).first()
        db.add(DoctorHospitalAffiliation(doctor_id=doc.id, hospital_id=hospitals[hidx - 1].id,
                                         department_id=dept.id if dept else None,
                                         opd_days=opd_days, consultation_hours=hours))
        doctors[name] = doc

    staff_users = {}
    for name, hidx, desig, dept in STAFF:
        u = User(role="STAFF", name=name, worker_id=f"STF{len(staff_users)+201:03d}",
                 password_hash=pw_hash)
        db.add(u)
        db.flush()
        staff_users[name] = u
        db.add(HospitalStaff(user_id=u.id, hospital_id=hospitals[hidx - 1].id,
                             designation=desig, department=dept))

    admin = User(role="ADMIN", name="Vijay Anand", worker_id="ADM001", password_hash=pw_hash)
    chw_user = User(role="CHW", name="Selvi Amirtham", worker_id="CHW042", password_hash=pw_hash)
    db.add_all([admin, chw_user])
    db.flush()
    db.add(HospitalAdmin(user_id=admin.id, hospital_id=hospitals[0].id))
    chw = CommunityHealthWorker(user_id=chw_user.id, worker_id="CHW042",
                                organization="Chennai City Community Health Programme (demo)",
                                region="Adyar & Thiruvanmiyur")
    db.add(chw)

    # ------------------------------------------------------------ patients
    # Patient 1 — app user (Arumugam, 68, orthopaedic + cardiac history).
    u1 = User(role="USER", name="Arumugam Subramani", phone="+919840000001", password_hash=pw_hash,
              onboarded=True)
    u2 = User(role="CAREGIVER", name="Divya Subramani", phone="+919840000002", password_hash=pw_hash,
              onboarded=True)
    db.add_all([u1, u2])
    db.flush()
    db.add(UserProfile(user_id=u1.id, date_of_birth=date(1958, 3, 14), blood_group="O+",
                       preferred_language="Tamil", location_text="Adyar, Chennai",
                       latitude=13.0012, longitude=80.2565,
                       relationship_to_care="Myself"))
    db.add(UserProfile(user_id=u2.id, date_of_birth=date(1990, 7, 2),
                       location_text="Adyar, Chennai", relationship_to_care="Daughter"))

    p1 = Patient(user_id=u1.id, display_name="Arumugam Subramani", date_of_birth=date(1958, 3, 14),
                 blood_group="O+", preferred_language="Tamil", location_text="Adyar, Chennai",
                 latitude=13.0012, longitude=80.2565,
                 emergency_contact_name="Divya Subramani",
                 emergency_contact_phone="+919840000002", emergency_contact_relation="Daughter")
    db.add(p1)
    db.flush()

    # Patient 2 — elderly, app-managed by CHW workflow (Kamala).
    p2 = Patient(display_name="Kamala Devi", date_of_birth=date(1950, 11, 8), blood_group="B+",
                 preferred_language="Tamil", location_text="Thiruvanmiyur, Chennai",
                 latitude=12.9830, longitude=80.2594,
                 emergency_contact_name="Ramesh Devi", emergency_contact_phone="+919840000003",
                 emergency_contact_relation="Son")
    db.add(p2)
    db.flush()

    # Conditions / allergies — synthetic but internally consistent.
    db.add_all([
        MedicalCondition(patient_id=p1.id, condition="Type 2 Diabetes Mellitus",
                         speciality_key="general_medicine", diagnosed_on=date(2015, 6, 1),
                         status="MANAGED", source="USER_REPORTED",
                         notes="On oral hypoglycaemics, last HbA1c 6.9% (demo report)"),
        MedicalCondition(patient_id=p1.id, condition="Osteoarthritis — both knees",
                         speciality_key="orthopaedics", diagnosed_on=date(2021, 2, 20),
                         status="ACTIVE", source="USER_REPORTED",
                         notes="Bilateral knee pain, worse on stairs"),
        MedicalCondition(patient_id=p1.id, condition="Hypertension",
                         speciality_key="cardiology", diagnosed_on=date(2018, 9, 10),
                         status="MANAGED", source="USER_REPORTED"),
        MedicalCondition(patient_id=p2.id, condition="Post-operative breast cancer follow-up",
                         speciality_key="oncology", diagnosed_on=date(2019, 4, 15),
                         status="MANAGED", source="PROTOTYPE_CLINICAL"),
        MedicalCondition(patient_id=p2.id, condition="Osteoporosis",
                         speciality_key="orthopaedics", diagnosed_on=date(2020, 8, 3),
                         status="MANAGED", source="PROTOTYPE_CLINICAL"),
    ])
    db.add_all([
        Allergy(patient_id=p1.id, allergen="Sulfa drugs", severity="SEVERE",
                reaction="Rash, swelling — reported by patient"),
        Allergy(patient_id=p2.id, allergen="Penicillin", severity="MODERATE",
                reaction="Skin rash (demo record)"),
    ])
    db.flush()

    # ------------------------------------------------- caregiver access
    rel = CaregiverRelationship(caregiver_user_id=u2.id, patient_id=p1.id,
                                relationship="Daughter", status="ACTIVE")
    db.add(rel)
    db.flush()
    granted = ["view_appointments", "request_appointments", "view_prescriptions",
               "view_medications", "assist_medication", "assist_navigation", "emergency_assist"]
    for perm in ["view_appointments", "request_appointments", "view_prescriptions",
                 "view_medications", "view_health_logs", "assist_medication",
                 "assist_navigation", "emergency_assist", "contact_emergency_person"]:
        db.add(CaregiverPermission(relationship_id=rel.id, permission=perm,
                                   granted=perm in granted))

    # ------------------------------------------------ CHW assignment
    db.add(CommunityAssignment(chw_id=chw.id, patient_id=p2.id, priority="WELLNESS_DUE"))

    # ------------------------------------------------- health memory data
    db.add_all([
        Medication(patient_id=p1.id, name="Metformin 500mg", dosage="1 tablet",
                   frequency="Twice daily after food", start_date=date(2015, 6, 10),
                   status="ACTIVE", prescribed_by="Dr. Priya Venkatesan"),
        Medication(patient_id=p1.id, name="Telmisartan 40mg", dosage="1 tablet",
                   frequency="Once daily morning", start_date=date(2018, 9, 12),
                   status="ACTIVE", prescribed_by="Dr. Suresh Balaji"),
        Medication(patient_id=p1.id, name="Calcium + Vitamin D3", dosage="1 tablet",
                   frequency="Once daily", start_date=_date(today, -120), status="ACTIVE",
                   prescribed_by="Dr. Aravind Kumar"),
        Medication(patient_id=p2.id, name="Calcium + Vitamin D3", dosage="1 tablet",
                   frequency="Once daily", start_date=_date(today, -200), status="ACTIVE",
                   prescribed_by="Dr. Aravind Kumar"),
        Medication(patient_id=p2.id, name="Alendronate 70mg", dosage="1 tablet weekly",
                   frequency="Once weekly", start_date=_date(today, -180), status="ACTIVE",
                   prescribed_by="Dr. Meera Raghavan"),
    ])

    # Daily health logs — 12 days for p1, then a gap (wellness follow-up demo for p2).
    for i in range(12, 0, -1):
        pain = 6 if i > 8 else (5 if i > 4 else 4)
        db.add(HealthLog(patient_id=p1.id, logged_at=datetime.now() - timedelta(days=i, hours=3),
                         pain_level=pain, temperature_c=36.8, mood="Okay" if pain < 6 else "Tired",
                         symptoms="Knee pain while climbing stairs" if pain >= 5 else "Mild knee stiffness",
                         adherence="TAKEN_ALL", notes="Walking short distances"))
    db.add(HealthLog(patient_id=p1.id, logged_at=datetime.now() - timedelta(hours=26),
                     pain_level=3, temperature_c=36.6, mood="Good",
                     symptoms="Less knee pain today", adherence="TAKEN_ALL",
                     notes="Started morning walk"))

    # Reports (synthetic demo documents).
    def _demo_file(title: str, body: str) -> bytes:
        return (f"CAREROUTE DEMO DOCUMENT — {title}\n"
                f"{'=' * 60}\n{body}\n\nThis is a synthetic demonstration document "
                f"generated inside the CareRoute prototype. Not real patient data.\n").encode()

    db.add_all([
        MedicalReport(patient_id=p1.id, title="Bilateral Knee X-ray", report_type="IMAGING",
                      speciality_key="orthopaedics", hospital_id=hospitals[0].id,
                      doctor_id=doctors["Dr. Aravind Kumar"].id, report_date=_date(today, -150),
                      summary="Joint space narrowing, bilateral knee osteoarthritis (demo)",
                      findings="Grade 2 changes both knees, no acute fracture (demo report)",
                      file_name="knee_xray_demo.txt", content_type="text/plain",
                      file_data=_demo_file("Bilateral Knee X-ray",
                                           "Impression: Grade 2 osteoarthritic changes, both knees."),
                      data_source="PROTOTYPE_UPLOAD"),
        MedicalReport(patient_id=p1.id, title="HbA1c Laboratory Report", report_type="LAB",
                      speciality_key="general_medicine", hospital_id=hospitals[1].id,
                      report_date=_date(today, -60), summary="HbA1c 6.9% (demo)",
                      findings="Consistent with moderately controlled diabetes (demo report)",
                      file_name="hba1c_demo.txt", content_type="text/plain",
                      file_data=_demo_file("HbA1c", "Result: 6.9 % (reference < 5.7 %)"),
                      data_source="PROTOTYPE_UPLOAD"),
        MedicalReport(patient_id=p2.id, title="Mammography Follow-up", report_type="IMAGING",
                      speciality_key="oncology", hospital_id=hospitals[2].id,
                      doctor_id=doctors["Dr. Lakshmi Narayanan"].id, report_date=_date(today, -90),
                      summary="No recurrence detected (demo)", findings="BIRADS 2, routine follow-up (demo)",
                      file_name="mammo_demo.txt", content_type="text/plain",
                      file_data=_demo_file("Mammography", "Routine surveillance, no suspicious findings."),
                      data_source="PROTOTYPE_UPLOAD"),
    ])
    db.flush()

    # -------------------------------------------------- appointments
    a1 = Appointment(patient_id=p1.id, doctor_id=doctors["Dr. Aravind Kumar"].id,
                     hospital_id=hospitals[0].id,
                     department_id=db.query(HospitalDepartment).filter_by(
                         hospital_id=hospitals[0].id, speciality_key="orthopaedics").first().id,
                     requested_by_user_id=u1.id, requested_on_behalf="SELF",
                     appointment_date=_date(today, 2), time_slot="10:00 - 10:30",
                     status="CONFIRMED", reason="Knee pain follow-up", token_number="T-14")
    a2 = Appointment(patient_id=p1.id, doctor_id=doctors["Dr. Suresh Balaji"].id,
                     hospital_id=hospitals[0].id,
                     department_id=db.query(HospitalDepartment).filter_by(
                         hospital_id=hospitals[0].id, speciality_key="cardiology").first().id,
                     requested_by_user_id=u1.id, requested_on_behalf="SELF",
                     appointment_date=_date(today, 9), time_slot="09:30 - 10:00",
                     status="REQUESTED", reason="Routine BP review")
    a3 = Appointment(patient_id=p1.id, doctor_id=doctors["Dr. Priya Venkatesan"].id,
                     hospital_id=hospitals[0].id,
                     department_id=db.query(HospitalDepartment).filter_by(
                         hospital_id=hospitals[0].id, speciality_key="general_medicine").first().id,
                     requested_by_user_id=u1.id, requested_on_behalf="SELF",
                     appointment_date=_date(today, -40), time_slot="11:00 - 11:30",
                     status="COMPLETED", reason="Diabetes review", token_number="T-07")
    db.add_all([a1, a2, a3])
    db.flush()

    # Prescription attached to the completed encounter (consistent chain).
    rx = Prescription(patient_id=p1.id, doctor_id=doctors["Dr. Priya Venkatesan"].id,
                      hospital_id=hospitals[0].id, appointment_id=a3.id,
                      issued_at=datetime.now() - timedelta(days=40),
                      diagnosis_text="Type 2 Diabetes Mellitus — review",
                      instructions="Continue diet control. Review HbA1c after 3 months.",
                      follow_up_on=_date(today, 50))
    db.add(rx)
    db.flush()
    db.add_all([
        PrescriptionItem(prescription_id=rx.id, medicine="Metformin 500mg", dosage="1 tablet",
                         frequency="Twice daily after food", duration_days=90,
                         instructions="After breakfast and dinner"),
        PrescriptionItem(prescription_id=rx.id, medicine="Vitamin B12", dosage="1 tablet",
                         frequency="Once daily", duration_days=90, instructions="After lunch"),
    ])

    # An earlier orthopaedic encounter (feeds the Clinical Snapshot demo).
    a4 = Appointment(patient_id=p1.id, doctor_id=doctors["Dr. Aravind Kumar"].id,
                     hospital_id=hospitals[0].id,
                     department_id=db.query(HospitalDepartment).filter_by(
                         hospital_id=hospitals[0].id, speciality_key="orthopaedics").first().id,
                     requested_by_user_id=u1.id, requested_on_behalf="SELF",
                     appointment_date=_date(today, -150), time_slot="10:30 - 11:00",
                     status="COMPLETED", reason="Bilateral knee pain", token_number="T-03")
    db.add(a4)
    db.flush()
    rx2 = Prescription(patient_id=p1.id, doctor_id=doctors["Dr. Aravind Kumar"].id,
                       hospital_id=hospitals[0].id, appointment_id=a4.id,
                       issued_at=datetime.now() - timedelta(days=150),
                       diagnosis_text="Bilateral knee osteoarthritis",
                       instructions="Physiotherapy twice weekly. Avoid stairs where possible.",
                       follow_up_on=_date(today, 2))
    db.add(rx2)
    db.flush()
    db.add(PrescriptionItem(prescription_id=rx2.id, medicine="Calcium + Vitamin D3",
                            dosage="1 tablet", frequency="Once daily", duration_days=180,
                            instructions="After food"))

    # Emergency contacts & historical emergency event (resolved).
    db.add_all([
        EmergencyContact(patient_id=p1.id, name="Divya Subramani", phone="+919840000002",
                         relationship="Daughter", is_primary=True),
        EmergencyContact(patient_id=p2.id, name="Ramesh Devi", phone="+919840000003",
                         relationship="Son", is_primary=True),
    ])
    db.add(EmergencyEvent(patient_id=p2.id, triggered_at=datetime.now() - timedelta(days=20),
                          latitude=12.9830, longitude=80.2594,
                          location_text="Thiruvanmiyur, Chennai",
                          situation="Fell at home, hip pain", status="RESOLVED",
                          summary={"name": "Kamala Devi", "blood_group": "B+",
                                   "allergies": ["Penicillin"],
                                   "critical": ["Post-operative breast cancer follow-up", "Osteoporosis"]},
                          voice_script="This is an emergency assistance request. The person is "
                                       "Kamala Devi, located at Thiruvanmiyur, Chennai. Reported "
                                       "situation: fell at home with hip pain. Emergency contact "
                                       "is Ramesh Devi at +919840000003.",
                          facility_hospital_id=hospitals[0].id, resolved_at=datetime.now() - timedelta(days=19)))

    # Community visit history.
    db.add(CommunityVisit(chw_id=chw.id, patient_id=p2.id, visit_date=_date(today, -14),
                          wellness_status="WELL", observations="Recovering well, medication taken regularly",
                          follow_up_on=_date(today, -1)))

    # Medical camps — clearly labeled controlled demo entries.
    db.add_all([
        MedicalCamp(name="Free Bone & Joint Screening Camp (demo entry)", camp_date=_date(today, 7),
                    location_text="Community Hall, Adyar, Chennai", latitude=13.0012, longitude=80.2565,
                    speciality="Orthopaedics", services="Free knee/hip consultation, bone density info",
                    organizer="CareRoute demo programme listing", registration="Walk-in",
                    contact="044-25305000", verified_source="Demo entry — verify with organizer"),
        MedicalCamp(name="Diabetes & BP Awareness Camp (demo entry)", camp_date=_date(today, 12),
                    location_text="Thiruvanmiyur, Chennai", latitude=12.9830, longitude=80.2594,
                    speciality="General Medicine", services="Blood sugar check, BP check, diet advice",
                    organizer="CareRoute demo programme listing", registration="Walk-in",
                    contact="044-40401066", verified_source="Demo entry — verify with organizer"),
    ])

    # Data source registry + notifications.
    db.add_all([
        DataSource(name="Prototype Hospital Provider", provider_type="PROTOTYPE",
                   status="CONNECTED", scope="Demo hospitals, appointments, clinical records",
                   last_synced_at=datetime.now(),
                   config={"note": "Controlled demonstration data; live operational feeds absent"}),
        DataSource(name="Authorized Hospital API (HL7 FHIR R4)", provider_type="AUTHORIZED_HOSPITAL_API",
                   status="PLANNED", scope="Future authorized integration point",
                   config={"standards": ["FHIR R4"], "note": "Not connected — reserved interface"}),
        DataSource(name="Official Emergency Services", provider_type="EMERGENCY_SERVICES",
                   status="PLANNED", scope="Future official emergency integration",
                   config={"note": "No official 108 integration exists in this prototype"}),
        DataSource(name="Live Bed/Queue Feeds", provider_type="HOSPITAL_OPS_LIVE",
                   status="UNAVAILABLE", scope="Live operational availability",
                   config={"note": "No live feed — UI shows 'Live availability unavailable'"}),
    ])
    db.add_all([
        Notification(user_id=u1.id, type="APPOINTMENT_CONFIRMED",
                     title="Appointment confirmed",
                     body="Your orthopaedics appointment with Dr. Aravind Kumar at Rajiv Gandhi "
                          "Government General Hospital on " + _date(today, 2).strftime("%d %b %Y") +
                          " at 10:00 is confirmed."),
        Notification(user_id=u2.id, type="APPOINTMENT_CONFIRMED",
                     title="Appa's appointment confirmed",
                     body="Orthopaedics follow-up at RGGGH, " + _date(today, 2).strftime("%d %b") + " 10:00 AM."),
        Notification(user_id=chw_user.id, type="WELLNESS_FOLLOWUP",
                     title="Wellness follow-up due",
                     body="Kamala Devi has no recent activity — wellness follow-up required."),
    ])

    # Device credential demo enrollment + refresh token.
    db.add(DeviceCredential(user_id=u1.id, device_name="Demo Laptop",
                            secret_hash=hash_password("demo-device-secret")))
    db.add_all([
        __import__("models").RefreshToken(user_id=u1.id, token_hash=refresh,
                                          expires_at=datetime.now() + timedelta(days=7)),
        __import__("models").RefreshToken(user_id=u2.id, token_hash=refresh,
                                          expires_at=datetime.now() + timedelta(days=7)),
    ])

    # ------------------------------------------------------ clean demo workflow
    # Do not pre-populate the doctor dashboard with synthetic future patients.
    # The four/five-laptop demonstration must create the relationship through the
    # real workflow: patient/authorized helper -> appointment request -> hospital
    # staff confirmation -> doctor sees that confirmed patient.
    # Keep the user/caregiver/CHW identities above so the demo can log in, but start
    # the clinical and appointment records empty. The patient creates real prototype
    # records during the demonstration.
    patient_ids = [p1.id, p2.id]
    prescription_ids = [r[0] for r in db.query(Prescription.id).filter(Prescription.patient_id.in_(patient_ids)).all()]
    if prescription_ids:
        db.query(PrescriptionItem).filter(PrescriptionItem.prescription_id.in_(prescription_ids)).delete(synchronize_session=False)
        db.query(Prescription).filter(Prescription.id.in_(prescription_ids)).delete(synchronize_session=False)
    db.query(Appointment).filter(Appointment.patient_id.in_(patient_ids)).delete(synchronize_session=False)
    db.query(HealthLog).filter(HealthLog.patient_id.in_(patient_ids)).delete(synchronize_session=False)
    db.query(MedicalReport).filter(MedicalReport.patient_id.in_(patient_ids)).delete(synchronize_session=False)
    db.query(Medication).filter(Medication.patient_id.in_(patient_ids)).delete(synchronize_session=False)
    db.query(MedicalCondition).filter(MedicalCondition.patient_id.in_(patient_ids)).delete(synchronize_session=False)
    db.query(Allergy).filter(Allergy.patient_id.in_(patient_ids)).delete(synchronize_session=False)
    db.query(EmergencyEvent).filter(EmergencyEvent.patient_id.in_(patient_ids)).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.user_id.in_([u1.id, u2.id]),
                                  Notification.type.in_(["APPOINTMENT_CONFIRMED", "APPOINTMENT_REQUESTED", "APPOINTMENT_REJECTED"])).delete(synchronize_session=False)

    # Seed audit entry.
    db.add(AuditLog(action="SYSTEM_SEED", actor_role="SYSTEM", result="ALLOWED",
                    detail="Prototype dataset initialized with verified hospital info + synthetic records",
                    device="seed", ip="127.0.0.1"))

    db.commit()
    hospital_names = [h.name for h in hospitals]
    db.close()
    print("Seed complete:")
    print("  Hospitals:", hospital_names)
    print(f"  Demo logins — password for all: {PW}")
    print("   USER  phone +919840000001 (Arumugam, patient)")
    print("   CAREGIVER phone +919840000002 (Divya, daughter)")
    print("   STAFF  STF201 (Latha, RGGGH reception) | STF202 (Apollo) | STF203 (Cancer Institute)")
    print("   DOCTOR DOC101 Dr. Aravind Kumar (Ortho, RGGGH) | DOC104 Dr. Meera Raghavan (Ortho, Apollo)")
    print("   ADMIN  ADM001 (RGGGH)")
    print("   CHW    CHW042 (Selvi, assigned: Kamala Devi)")


if __name__ == "__main__":
    seed()
