"""End-to-end test of CareRoute AI demo flows (runs against the real app, in-process)."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_careroute.db")
if os.path.exists("test_careroute.db"):
    os.remove("test_careroute.db")

import seed
seed.seed()

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
PASS = []
FAIL = []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name + (f"  [{extra}]" if extra and not cond else ""))


def login(identifier, otp_code=None):
    r = client.post("/auth/request-otp", json={"identifier": identifier})
    assert r.status_code == 200, r.text
    code = otp_code or r.json()["demo_otp"]
    r = client.post("/auth/verify-otp", json={"identifier": identifier, "code": code})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


# ---------------------------------------------------------------- Demo 1: routine appointment
user = login("+919840000001")
r = client.get("/auth/me", headers=user)
check("user login + identity", r.status_code == 200 and r.json()["role"] == "USER")

r = client.post("/find-care/suggest", json={"concern": "knee pain while climbing stairs"})
check("find-care suggests orthopaedics", r.status_code == 200
      and any(s["speciality_key"] == "orthopaedics" for s in r.json()["suggestions"]))

# Directory semantics (speciality filter) are demo-provider behavior — opt in explicitly.
_saved_provider0 = os.environ.get("CAREROUTE_PROVIDER")
os.environ["CAREROUTE_PROVIDER"] = "prototype"
r = client.get("/hospitals", params={"speciality": "orthopaedics", "lat": 13.0012, "lng": 80.2565})
hospitals = r.json()["hospitals"]
os.environ["CAREROUTE_PROVIDER"] = _saved_provider0 if _saved_provider0 is not None else "overpass"
check("hospital directory filters by speciality (demo provider)", r.status_code == 200 and len(hospitals) >= 2
      and hospitals[0]["distance_km"] is not None)

r = client.get("/doctors", params={"speciality": "orthopaedics", "hospital_id": 1})
docs = r.json()["doctors"]
check("doctor directory (ortho, RGGGH)", r.status_code == 200 and len(docs) == 1)
doc = docs[0]

r = client.get("/hospitals/1/availability/beds")
check("live availability honest state", r.status_code == 200 and r.json()["available"] is False)

from datetime import date, datetime, timedelta
future = str(date.today() + timedelta(days=6))
r = client.post("/appointments", headers=user, json={
    "doctor_id": doc["doctor_id"], "appointment_date": future, "time_slot": "15:00 - 15:30",
    "reason": "Knee pain worsening"})
check("patient requests appointment", r.status_code == 200 and r.json()["status"] == "REQUESTED",
      r.text[:200])
appt_id = r.json()["id"]

staff = login("STF201")
r = client.get("/appointments", headers=staff)
check("staff sees pending request", r.status_code == 200
      and any(a["id"] == appt_id and a["status"] == "REQUESTED" for a in r.json()["appointments"]))

r = client.post(f"/appointments/{appt_id}/confirm", headers=staff, json={"note": "Confirmed, OPD 2"})
check("staff confirms appointment", r.status_code == 200 and r.json()["status"] == "CONFIRMED")

r = client.get("/appointments", headers=user)
check("patient sees confirmation + token", any(
    a["id"] == appt_id and a["status"] == "CONFIRMED" and a["token_number"]
    for a in r.json()["appointments"]))

r = client.get("/notifications", headers=user)
check("patient notified of confirmation", any(
    n["type"] == "APPOINTMENT_CONFIRMED" for n in r.json()["notifications"]))

# Doctor sees the appointment (Laptop 3)
doctor = login("DOC101")
r = client.get("/appointments", headers=doctor)
check("doctor sees scheduled appointment", r.status_code == 200
      and any(a["id"] == appt_id for a in r.json()["appointments"]))

# ---------------------------------------------------------------- Demo 2: clinical snapshot + prescription
r = client.get(f"/clinical-snapshot/{1}", params={"speciality_key": "orthopaedics"}, headers=doctor)
snap = r.json()
check("clinical snapshot (ortho-filtered)", r.status_code == 200
      and snap["speciality_filter"] == "orthopaedics"
      and any(c["condition"].startswith("Osteoarthritis") for c in snap["conditions"]))
check("snapshot includes allergies", any(a["allergen"] == "Sulfa drugs" for a in snap["allergies"]))
check("snapshot has AI summary (deterministic)", "snapshot" in snap.get("ai_summary", {}))

r = client.get(f"/reports", params={"patient_id": 1, "speciality_key": "orthopaedics"}, headers=doctor)
check("doctor sees only ortho reports", r.status_code == 200
      and all(rep["speciality_key"] == "orthopaedics" for rep in r.json()["reports"]))

r = client.post("/prescriptions", headers=doctor, json={
    "patient_id": 1, "appointment_id": appt_id, "diagnosis_text": "Knee OA review",
    "instructions": "Continue physiotherapy",
    "items": [{"medicine": "Paracetamol 650mg", "dosage": "1 tablet", "frequency": "Twice daily",
               "duration_days": 7, "instructions": "After food"}]})
check("doctor creates prescription", r.status_code == 200, r.text[:200])
rx_id = r.json()["id"]

r = client.get("/prescriptions", headers=user)
check("patient receives prescription", any(p["id"] == rx_id for p in r.json()["prescriptions"]))
r = client.get("/notifications", headers=user)
check("prescription notification", any(n["type"] == "PRESCRIPTION_AVAILABLE"
                                       for n in r.json()["notifications"]))

# Cross-speciality guard: ortho doctor must NOT see cardiology-filtered snapshot freely
r = client.get(f"/clinical-snapshot/{1}", params={"speciality_key": "cardiology"}, headers=doctor)
check("cross-speciality access denied", r.status_code == 403)

# ---------------------------------------------------------------- Demo 3: caregiver
cg = login("+919840000002")
r = client.get("/caregivers/my-patients", headers=cg)
mine = r.json()["patients"]
check("caregiver sees authorized patient + perms", r.status_code == 200 and len(mine) == 1
      and "view_prescriptions" in mine[0]["permissions"])
r = client.get("/prescriptions", headers=cg)
check("caregiver sees authorized prescriptions", r.status_code == 200
      and any(p["id"] == rx_id for p in r.json()["prescriptions"]))
r = client.get("/reports", headers=cg)
check("caregiver denied sensitive reports", r.status_code == 403)
r = client.get("/health-memory/1", headers=cg)
hm = r.json()
check("caregiver health memory is scope-filtered (no conditions/logs, meds only)",
      r.status_code == 200 and hm["conditions"] == [] and hm["allergies"] == []
      and hm["health_logs"] == [] and len(hm["medications"]) > 0)

# Patient modifies permissions: grant view_health_logs, verify it appears
r = client.get("/caregivers", headers=user)
rel_id = r.json()["caregivers"][0]["relationship_id"]
perms = [k for k, v in r.json()["caregivers"][0]["permissions"].items() if v]
r = client.put(f"/caregivers/{rel_id}/permissions", headers=user,
               json={"permissions": perms + ["view_health_logs"]})
check("patient modifies caregiver permissions", r.status_code == 200)
r = client.get("/health-memory/1", headers=cg)
hm = r.json()
check("caregiver health-log access after grant", r.status_code == 200 and len(hm["health_logs"]) > 0)

# Revoke then verify denial
r = client.post(f"/caregivers/{rel_id}/revoke", headers=user)
check("patient revokes caregiver", r.status_code == 200)
r = client.get("/prescriptions", headers=cg)
check("caregiver blocked after revoke", r.status_code == 403)
# restore for subsequent demos
client.put(f"/caregivers/{rel_id}/permissions", headers=user, json={"permissions": perms + ["view_health_logs"]})
import database
db = database.SessionLocal()
from models import CaregiverRelationship
rel = db.query(CaregiverRelationship).get(rel_id)
rel.status = "ACTIVE"
db.commit(); db.close()

# ---------------------------------------------------------------- Demo 4: community health
chw = login("CHW042")
r = client.get("/community-care/assigned", headers=chw)
assigned = r.json()["assigned"]
check("CHW sees assigned users", r.status_code == 200 and len(assigned) == 1
      and assigned[0]["name"] == "Kamala Devi")
check("inactivity → wellness follow-up (not emergency)",
      assigned[0]["wellness_follow_up_required"] is True
      and "emergency" not in assigned[0]["note"].lower())

r = client.post("/community-care/visit", headers=chw, json={
    "patient_id": assigned[0]["patient_id"], "wellness_status": "NEEDS_ATTENTION",
    "observations": "Knee pain making walks difficult;BP borderline",
    "follow_up_on": str(date.today() + timedelta(days=7))})
check("CHW records visit", r.status_code == 200)

r = client.post("/appointments", headers=chw, json={
    "patient_id": assigned[0]["patient_id"], "doctor_id": 2,  # Dr. Priya, general medicine
    "appointment_date": str(date.today() + timedelta(days=8)), "time_slot": "11:00 - 11:30",
    "reason": "Elderly wellness review (CHW assisted)"})
check("CHW requests appointment for user", r.status_code == 200, r.text[:200])
chw_appt = r.json()["id"]
r = client.post(f"/appointments/{chw_appt}/confirm", headers=staff, json={"note": "OK"})
check("staff confirms CHW request", r.status_code == 200 and r.json()["status"] == "CONFIRMED")

# ---------------------------------------------------------------- Demo 5: emergency
r = client.post("/emergency/trigger", headers=user, json={
    "latitude": 13.0090, "longitude": 80.2500, "location_text": "Besant Nagar, Chennai",
    "situation": "Chest discomfort and sweating"})
er = r.json()
check("emergency triggers", r.status_code == 200 and er["event_id"] > 0)
check("emergency summary is minimum-necessary", set(er["summary"]) >= {
    "name", "blood_group", "allergies", "critical_conditions", "emergency_contact"})
check("emergency summary contains allergies", any(a["allergen"] == "Sulfa drugs"
                                                  for a in er["summary"]["allergies"]))
check("ambulance live status honest", er["ambulance_status"]["available"] is False)
# Emergency facilities: live nearby search with honest failure handling —
# when the live provider is rate-limited/unreachable the response carries an
# honest note (and NO fabricated facilities) instead of demo fallbacks.
if er["facilities"]:
    check("emergency facilities ranked by distance",
          all(f["distance_km"] is not None for f in er["facilities"])
          and er["facilities"][0]["distance_km"] <= er["facilities"][-1]["distance_km"])
    check("emergency facilities carry source metadata",
          all(f.get("data_source") for f in er["facilities"]))
else:
    check("(live-unreachable) emergency facilities honest empty + note",
          bool(er.get("facilities_note")) and er["facilities"] == [])
ev_id = er["event_id"]

r = client.get(f"/emergency/{ev_id}/voice-script", headers=user)
check("AI voice script prepared", r.status_code == 200 and "emergency assistance request"
      in r.json()["voice_script"])

# QR emergency feature REMOVED by design (§26): the route must be gone from the API.
_paths = client.get("/openapi.json").json()["paths"]
check("emergency QR removed", not any("/emergency/qr" in p for p in _paths))

r = client.post(f"/emergency/{ev_id}/resolve", headers=user)
check("emergency resolved", r.status_code == 200)

# Caregiver with emergency_assist may trigger
r = client.post("/emergency/trigger", headers=cg, json={"patient_id": 1, "situation": "Fall at home"})
check("caregiver emergency assist allowed", r.status_code == 200)
client.post(f"/emergency/{r.json()['event_id']}/resolve", headers=user)

# ---------------------------------------------------------------- Break-glass
r = client.post("/emergency-access/invoke", headers=staff, json={
    "patient_id": 1, "reason": "Unconscious patient at reception, need allergy info"})
bg = r.json()
check("staff invokes break-glass", r.status_code == 200 and "expires_at" in bg)
r = client.post(f"/emergency-access/{bg['break_glass_id']}/justify", headers=staff,
                json={"justification": "Patient unable to communicate; verified identity by ID card"})
check("post-event justification recorded", r.status_code == 200)

# User sees the break-glass event in privacy center
r = client.get("/privacy/overview", headers=user)
check("break-glass visible in patient privacy center", r.status_code == 200
      and any(e["id"] == bg["break_glass_id"] for e in r.json()["break_glass_events"]))

# ---------------------------------------------------------------- Authorization negative tests
r = client.get("/health-memory/2", headers=user)  # another patient's record
check("user cannot read another patient", r.status_code == 403)
r = client.get("/appointments", headers=(user2 := login("+919840000003")))  # stranger phone → new acct
check("stranger account gets empty scope", r.status_code == 200 and r.json()["appointments"] == [])
r = client.get("/admin/overview", headers=staff)
check("staff cannot access admin endpoints", r.status_code == 403)
r = client.get("/admin/overview")
check("unauthenticated blocked", r.status_code == 401)

# CHW cannot access unassigned patient
r = client.get("/health-memory/1", headers=chw)
check("CHW blocked from unassigned clinical detail", r.status_code == 403)

# ---------------------------------------------------------------- Admin
admin = login("ADM001")
r = client.get("/admin/overview", headers=admin)
check("admin overview", r.status_code == 200 and r.json()["hospital"]["id"] == 1)
r = client.get("/admin/data-sources", headers=admin)
check("admin sees data source registry", r.status_code == 200
      and len(r.json()["data_sources"]) == 4
      and any(d["status"] == "PLANNED" for d in r.json()["data_sources"]))
r = client.post("/admin/staff", headers=admin, json={
    "name": "New Front Desk", "designation": "Receptionist", "department": "OPD"})
check("admin adds staff", r.status_code == 200 and r.json()["worker_id"].startswith("STF"))

# ---------------------------------------------------------------- Audit trail
r = client.get("/audit", headers=user)
actions = {a["action"] for a in r.json()["audit"]}
check("audit log populated", {"APPOINTMENT_REQUEST", "PRESCRIPTION_CREATED", "EMERGENCY_TRIGGERED",
                              "ACCESS_DENIED", "PERMISSION_REVOKED", "EMERGENCY_ACCESS"} <= actions,
      str(actions))

r = client.get("/fhir/mapping")
check("FHIR conceptual mapping exposed", r.status_code == 200 and "Patient" in r.json()["conceptual_map"])

r = client.get("/system/provider-status")
check("provider status honest", r.status_code == 200
      and r.json()["provider"]["mode"] in ("PROTOTYPE", "LIVE_NEARBY_SEARCH", "LIVE_DISCOVERY"))

# ------------------------------------------ LIVE SYNC + DYNAMIC DISCOVERY
# /sync token changes for the recipient when something new happens for them.
r = client.get("/sync", headers=user)
t_before = r.json()["sync_token"]
check("sync endpoint returns token", r.status_code == 200 and t_before
      and r.json()["poll_after_seconds"] >= 1)

# Deterministic probe: a new appointment request notifies the requester (user)
# and the hospital staff — both sync tokens must move.
r = client.get("/doctors", params={"speciality": "orthopaedics", "hospital_id": 1})
probe_doc = r.json()["doctors"][0]
r = client.post("/appointments", headers=user, json={
    "doctor_id": probe_doc["doctor_id"], "appointment_date": "2027-03-02",
    "time_slot": "09:00 - 09:30", "reason": "sync probe request"})
check("sync probe appointment accepted", r.status_code == 200, r.text[:150])
r = client.get("/sync", headers=user)
check("sync token reacts to new activity", r.status_code == 200
      and r.json()["sync_token"] != t_before,
      f"{t_before} -> {r.json().get('sync_token')}")

# Staff /sync is scoped to their hospital and works.
r = client.get("/sync", headers=staff)
check("staff sync token", r.status_code == 200 and r.json()["sync_token"])

# Places status reports the REAL active provider.
r = client.get("/places/status")
check("places status reports real provider", r.status_code == 200
      and r.json()["provider"] in ("OverpassProvider", "GooglePlacesProvider", "PrototypeHospitalProvider"))

# /hospitals keeps its directory contract for the demo workflow — run against the
# DEMO provider explicitly (live providers have no local directory; that is now the
# honest contract, not a failure).
_saved_provider2 = os.environ.get("CAREROUTE_PROVIDER")
os.environ["CAREROUTE_PROVIDER"] = "prototype"
r = client.get("/hospitals", params={"lat": 13.0012, "lng": 80.2565})
check("hospitals endpoint intact", r.status_code == 200 and len(r.json()["hospitals"]) >= 3)
os.environ["CAREROUTE_PROVIDER"] = "overpass"
r = client.get("/hospitals", params={"lat": 13.0012, "lng": 80.2565})
check("live provider failure = honest empty, never demo fallback", r.status_code == 200
      and r.json().get("provider_failed") is True and r.json()["hospitals"] == [])
os.environ["CAREROUTE_PROVIDER"] = _saved_provider2 if _saved_provider2 is not None else "overpass"

# -------------------------------------- HEALTH MEMORY TIMELINE / LOGS / MEDS
# Timeline is generated ONLY from real records and every event cites its source.
r = client.get(f"/health-memory/1", headers=user)
tl = r.json()["timeline"]
check("timeline generated from real records", r.status_code == 200 and isinstance(tl, list)
      and all(e.get("source") and e.get("ref") for e in tl)
      and all(e["kind"] in ("log", "appointment", "prescription", "report", "condition") for e in tl))
check("timeline has prescription + appointment events",
      any(e["kind"] == "prescription" for e in tl) and any(e["kind"] == "appointment" for e in tl))

# Medication taken-today flow (§9).
r = client.get("/health-memory/1", headers=user)
med0 = next(m for m in r.json()["medications"] if m["status"] == "ACTIVE")
check("medication exposes last_taken_on", "last_taken_on" in med0)
r = client.post(f"/medications/{med0['id']}/taken", headers=user)
check("mark medication taken today", r.status_code == 200
      and r.json()["last_taken_on"] == str(datetime.utcnow().date()))
r = client.get("/health-memory/1", headers=user)
med1 = next(m for m in r.json()["medications"] if m["id"] == med0["id"])
check("taken status persisted", med1["last_taken_on"] == str(datetime.utcnow().date()))

# New-user honesty: a fresh patient has an EMPTY memory — nothing pre-filled.
newuser = login("+919999000111")
r = client.post("/users/onboard", headers=newuser, json={
    "name": "Honest Tester", "date_of_birth": "1990-01-01", "phone": "+919999000111",
    "location_text": "Chennai", "relationship_to_care": "Myself",
    "conditions": [], "allergies": [], "medications": []})
check("new user onboards empty", r.status_code == 200, r.text[:150])
r = client.get(f"/health-memory/{r.json()['patient_id']}", headers=newuser)
nh = r.json()
check("new user memory empty (no fake history)", r.status_code == 200
      and nh["timeline"] == [] and nh["conditions"] == []
      and nh["medications"] == [] and nh["health_logs"] == [])

# Discover filters + why-surfaced chips (§3) — run against the DEMO provider explicitly
# (the default provider is the live Overpass search; these checks target directory
# semantics, so they opt in via CAREROUTE_PROVIDER=prototype).
_saved_provider = os.environ.get("CAREROUTE_PROVIDER")
os.environ["CAREROUTE_PROVIDER"] = "prototype"
r = client.get("/hospitals/discover", params={"lat": 13.0827, "lng": 80.2707, "multi_specialty": True})
check("discover multi_specialty filter", r.status_code == 200
      and all(len(f["departments"]) >= 4 for f in r.json()["facilities"]) and len(r.json()["facilities"]) >= 1)
r = client.get("/hospitals/discover", params={"lat": 13.0827, "lng": 80.2707})
fac0 = r.json()["facilities"][0]
check("discover why-chips present", r.status_code == 200 and fac0.get("why")
      and any("km away" in w for w in fac0["why"]))

# Location-aware medical camps (§19): distance + radius filtering.
r = client.get("/medical-camps", params={"lat": 13.0012, "lng": 80.2565, "radius_km": 2})
check("camps radius filtering works", r.status_code == 200
      and all(c["distance_km"] <= 2.0 for c in r.json()["camps"]))
r = client.get("/medical-camps", params={"lat": 8.1780, "lng": 77.5065, "radius_km": 2})  # Nagercoil
check("camps far location empty + honest", r.status_code == 200
      and r.json()["camps"] == [] and "No verified medical camps found nearby" in r.json()["empty_note"])
r = client.get("/medical-camps")
check("camps unlocated = honest location request, never a city-wide list", r.status_code == 200
      and r.json()["camps"] == [] and "Enable current location" in r.json()["empty_note"])
if _saved_provider is None:
    os.environ.pop("CAREROUTE_PROVIDER", None)
else:
    os.environ["CAREROUTE_PROVIDER"] = _saved_provider

# 'Highly rated' filter is honest in demo mode: OSM/Places rows carry no ratings →
# the filter must not claim ratings that don't exist.
os.environ["CAREROUTE_PROVIDER"] = "prototype"
r = client.get("/hospitals/discover", params={"lat": 13.0827, "lng": 80.2707, "highly_rated": True})
check("highly_rated filter honest (no invented ratings)", r.status_code == 200
      and all(f.get("public_rating") for f in r.json()["facilities"]))
if os.environ.get("CAREROUTE_PROVIDER") == "prototype":
    os.environ.pop("CAREROUTE_PROVIDER", None)

# ------------------------------------------- LOCATION → REAL HEALTHCARE SEARCH
# Default provider is the REAL Overpass (OpenStreetMap) live search — no demo
# fallback. Network-dependent checks degrade honestly if the API is unreachable.
r = client.get("/hospitals/discover", params={"lat": 13.00645, "lng": 80.25702, "radius_km": 5})
dlive = r.json()
if dlive["provider_failed"]:
    check("(skip) live overpass unreachable in this environment", True)
else:
    check("live search returns real nearby results", dlive["data_source"] == "OPENSTREETMAP_OVERPASS"
          and len(dlive["facilities"]) >= 1
          and all(f.get("place_id", "").startswith("osm/") for f in dlive["facilities"]))
    check("live results carry real coordinates + distance",
          all(f["latitude"] is not None and f["longitude"] is not None
              and f["distance_km"] is not None for f in dlive["facilities"]))
    # §10: results must actually be inside the requested radius.
    check("live results verified inside radius",
          all(f["distance_km"] <= 5 for f in dlive["in_radius"]))

# Location change MUST change results (TEST 1/TEST 11): two distant points must
# produce different facility sets when the live provider is reachable.
r2 = client.get("/hospitals/discover", params={"lat": 9.9252, "lng": 78.1198, "radius_km": 5})  # Madurai
nd2 = r2.json()
if not nd2["provider_failed"] and not dlive["provider_failed"]:
    names_a = {f["name"] for f in dlive["facilities"]}
    names_b = {f["name"] for f in nd2["facilities"]}
    check("location change changes real results", nd2["data_source"] == "OPENSTREETMAP_OVERPASS"
          and names_a != names_b, f"{sorted(names_a)[:2]} vs {sorted(names_b)[:2]}")
else:
    check("(skip) location-change needs live provider", True)

# §1: no silent demo fallback — Vellore 5 km must NOT surface Chennai demo hospitals.
r = client.get("/hospitals/discover", params={"lat": 12.9165, "lng": 79.1325, "radius_km": 5})
dv = r.json()
if dv["provider_failed"]:
    check("(skip) no-fallback check needs live provider", True)
else:
    demo_names = {"Rajiv Gandhi Government General Hospital", "Apollo Hospitals Greams Road",
                  "Cancer Institute (WIA), Adyar"}
    returned_names = {f["name"] for f in dv["facilities"]}
    check("no silent demo fallback for far location",
          dv["data_source"] == "OPENSTREETMAP_OVERPASS"
          and (not returned_names or not (returned_names & demo_names)),
          str(sorted(returned_names)[:3]))

# §1: demo directory is opt-in only via CAREROUTE_PROVIDER=prototype.
import providers as _providers_mod
_saved = os.environ.get("CAREROUTE_PROVIDER")
os.environ["CAREROUTE_PROVIDER"] = "prototype"
from providers import get_provider as _gp
_check_db = database.SessionLocal()
check("demo provider opt-in works", isinstance(_gp(_check_db), _providers_mod.PrototypeHospitalProvider))
_check_db.close()
if _saved is None:
    os.environ.pop("CAREROUTE_PROVIDER", None)
else:
    os.environ["CAREROUTE_PROVIDER"] = _saved

# No coordinates → honest needs_location state, not a demo list.
r = client.get("/hospitals/discover")
check("discover without location requests location honestly", r.status_code == 200
      and r.json().get("needs_location") is True and r.json()["facilities"] == [])

# Camps expansion hints (§13/§17).
r = client.get("/medical-camps", params={"lat": 8.1780, "lng": 77.5065, "radius_km": 2})
check("camps far-location empty + hints", r.status_code == 200
      and r.json()["camps"] == [] and r.json()["next_radius_km"] == 5)

# Doctor information honesty (§11): demo doctors are labeled as demo identities —
# never presented as real practitioners.
r = client.get("/doctors", params={"speciality": "orthopaedics", "hospital_id": 1})
check("doctor info labeled as demo identity", r.status_code == 200
      and len(r.json()["doctors"]) >= 1
      and all(d["verification_status"] == "DEMO_IDENTITY" for d in r.json()["doctors"]))

# --------------------- SECTION 2: HOSPITAL → DEPARTMENT → DOCTOR → REQUEST
# Hospital detail returns distance when the search location is passed.
r = client.get("/hospitals/1", params={"lat": 13.0827, "lng": 80.2707})
check("hospital detail includes distance", r.status_code == 200
      and r.json()["distance_km"] is not None)

# Doctors endpoint supports department scoping and returns department names.
r = client.get("/doctors", params={"hospital_id": 1})
alldocs = r.json()["doctors"]
withdept = [d for d in alldocs if d.get("department_name")]
check("doctors carry department names", r.status_code == 200 and len(withdept) >= 1)
if withdept:
    dept_id = withdept[0]["department_id"]
    # Department-scoped appointment request (§8).
    r = client.post("/appointments", headers=user, json={
        "doctor_id": withdept[0]["doctor_id"], "department_id": dept_id,
        "appointment_date": "2027-04-20", "time_slot": "10:00 - 10:30",
        "reason": "department-scoped request"})
    check("department-scoped appointment request", r.status_code == 200
          and r.json()["status"] == "REQUESTED", r.text[:150])
    dept_appt_id = r.json()["id"]
    # Wrong-hospital department guard.
    r = client.get("/hospitals")
    other_hosp_depts = [h["departments"] for h in r.json()["hospitals"] if h["id"] != 1]
    if other_hosp_depts and other_hosp_depts[0]:
        r = client.post("/appointments", headers=user, json={
            "doctor_id": withdept[0]["doctor_id"], "department_id": other_hosp_depts[0][0]["id"],
            "appointment_date": "2027-04-20", "time_slot": "11:00 - 11:30"})
        check("cross-hospital department rejected", r.status_code == 400)

    # Staff suggests another time → patient accepts (§12/§13).
    staff = login("STF201")
    r = client.post(f"/appointments/{dept_appt_id}/reschedule", headers=staff, json={
        "new_date": "2027-04-22", "new_slot": "14:00 - 14:30",
        "note": "Doctor OPD moved to afternoon"})
    check("staff suggests another time", r.status_code == 200
          and r.json()["status"] == "RESCHEDULED", r.text[:150])
    suggested = r.json()["id"]
    r = client.post(f"/appointments/{suggested}/accept-reschedule", headers=user, json={})
    check("patient accepts suggested time", r.status_code == 200
          and r.json()["status"] == "CONFIRMED" and r.json()["token_number"], r.text[:150])
    # Double-accept is not possible.
    r = client.post(f"/appointments/{suggested}/accept-reschedule", headers=user, json={})
    check("accept only once", r.status_code == 404)

print(f"\n{'=' * 60}\nPASS {len(PASS)} / FAIL {len(FAIL)}")
for f in FAIL:
    print("  FAIL:", f)
if not FAIL:
    print("ALL DEMO FLOWS GREEN")
