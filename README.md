# CareRoute AI

**One Care Journey. Every Right Connection.**

A production-oriented prototype of a **multi-hospital healthcare coordination platform**:
one user's care journey connected across hospitals, specialities, doctors, caregivers,
hospital staff and community health workers — with strict, context-aware privacy.

> ⚠️ This is a working **prototype**. Hospital identity information (name, address,
> phone, departments) is publicly verified. All clinical records, staff, doctors and
> patients are **synthetic demonstration data**. No live hospital feeds are connected;
> wherever live data would be required the UI honestly shows
> **"Live availability unavailable"**. CareRoute is not a medical device and does not
> diagnose, prescribe, or replace official emergency services.

---

## Quick start (single port, single command)

```bash
# 1. Backend (first run auto-creates and seeds the demo database)
cd backend
pip install -r requirements.txt
../.venv/Scripts/python -m uvicorn main:app --host 0.0.0.0 --port 8000   # Windows venv path
#   Linux/mac: source .venv/bin/activate && python -m uvicorn main:app --port 8000

# 2. Frontend (only needed when you change frontend code)
cd frontend
npm install
npm run build          # outputs to frontend/dist — served automatically by the backend

# Open http://localhost:8000
```

The FastAPI app serves both the API (`/auth`, `/hospitals`, `/appointments`, …) and the
built React frontend on **port 8000** — one URL, four laptops, same database.

### Production database

Set `DATABASE_URL` to a PostgreSQL instance (e.g.
`postgresql+psycopg://user:pass@host/db`) and uncomment `psycopg` in
`backend/requirements.txt`. The schema is identical; SQLite is only the zero-config demo default.

---

## Four-laptop demo

Open the same URL on four laptops and sign in with one click each:

| Laptop | Role | Identifier | Who |
|---|---|---|---|
| 1 | Patient (USER) | `+919840000001` | Arumugam, 68 — manages own care |
| 2 | Hospital Staff | `STF201` | Latha — Reception, RGGGH |
| 3 | Doctor | `DOC101` | Dr. Aravind Kumar — Orthopaedics, RGGGH |
| 4 | Hospital Admin | `ADM001` | Vijay Anand — RGGGH |
| — | Caregiver | `+919840000002` | Divya — daughter, limited access |
| — | Community Health Worker | `CHW042` | Selvi — assigned elderly users |

Sign-in is **OTP-based (MFA)**; in prototype mode the 6-digit code is displayed on
screen instead of being sent by SMS. A demo password exists in seed data but the login
flow is OTP-only.

### Demo story lines

1. **Routine appointment** — Patient: Find Care → "knee pain…" → Orthopaedics → RGGGH →
   Dr. Aravind → request. Reception sees the request instantly, confirms with a note.
   Patient gets the confirmation + token; Doctor sees the scheduled consult.
2. **Clinical Snapshot** — Doctor opens the consultation: allergy banner, ortho-scoped
   AI summary, relevant X-ray, trend of symptoms, past consults. Issues a prescription →
   it appears in the patient's (and authorized caregiver's) Prescriptions page immediately.
3. **Caregiver** — Divya sees appointments + authorized prescriptions + medications,
   is **denied** reports and conditions, and can trigger emergency assist for her father.
   Arumugam can grant/modify/revoke every permission and see every use in his Privacy Center.
4. **Community health** — CHW Selvi sees Kamala Devi with **"no recent activity → wellness
   follow-up required"** (never an automatic emergency), records a visit, requests an
   appointment on her behalf; reception confirms.
5. **Emergency** — Any of patient/caregiver: confirm → location → minimum-necessary
   Emergency Health Summary (allergies, critical conditions, meds, contact) → AI voice
   message (plays via device speech) → distance-ranked emergency-capable facilities with
   real navigation → limited Emergency QR as fallback. Honest
   *"Ambulance live status unavailable"* — no invented ETAs.
6. **Break-glass** — Staff/Doctor can invoke time-boxed emergency access with a reason;
   it auto-expires, requires post-event justification, and is visible in the patient's
   Privacy Center audit history.

### Live cross-dashboard sync

Every signed-in dashboard polls a cheap `/sync` token endpoint (~3s). When anything
happens for that user — new appointment request, confirmation, prescription, emergency
event — the token changes and **every open screen for that user refreshes itself**,
with an unread badge on the bell and a toast. On four laptops this is the "receptionist
*immediately* sees the request → user *immediately* sees confirmation" moment; no
manual refresh is needed anywhere in the demo.

### Dynamic hospital discovery (optional live mode)

`/hospitals/discover` implements LOCATION → NEED → FACILITIES → DISTANCE/RELEVANCE for
any location. Two interchangeable providers behind one interface:

- **Prototype directory (default, zero-config):** the verified demo hospitals with
  location-aware distance ranking, speciality/emergency filters, and lay-need text
  search ("eye emergency" → ophthalmology-capable facilities first).
- **Google Places live mode:** set `GOOGLE_MAPS_API_KEY` and the same endpoint returns
  live public place data (name, address, phone, website, public rating, open-now) for
  **any** location on earth. Clinical departments/doctors are never invented for live
  results, and live operational feeds still honestly report unavailable.

The UI shows a transparent banner stating which source produced the results and which
ranking factors ("CareRoute discovery factors") were applied — never a "best hospital"
score. Switch location (Use my location, or type any city) and everything re-queries:
hospital list, map markers, distances and navigation options.

## Architecture

```
Frontend (React+TS+Tailwind, served by FastAPI)
        │  JWT (30 min) + refresh rotation + OTP MFA
        ▼
CareRoute API (FastAPI) ── every endpoint authorization-checked
        │
Authorization Engine (authz.py)
   Identity + Role + Relationship + Permission + Purpose + Clinical context
        │                        │
        ▼                        ▼
HospitalDataProvider      AI service (ai_service.py)
   Prototype now            receives ONLY pre-authorized,
   AuthorizedHospital-      pre-filtered information;
   Provider (HL7 FHIR R4)   never decides access; degrades
   reserved                 to a transparent summarizer
        │
        ▼
SQLAlchemy models — normalized, FHIR-mappable (fhir.py mapping layer)
AuditLog on every sensitive decision; DataSources registry; honest live states
```

Key modules (backend/): `models.py` (30+ tables), `authz.py` (the access engine),
`main.py` (all endpoints), `providers.py` (provider abstraction incl. GooglePlacesProvider),
`ai_service.py` (guard-railed AI: Gemini-native or OpenAI-compatible), `seed.py`
(controlled demo dataset), `audit.py`, `fhir.py` (FHIR-readiness mapping),
`test_e2e.py` (68 end-to-end checks).

## Honest-data guarantees

- Hospital names/addresses/phones are from public sources (official district directory,
  hospital websites); `verified_fields` records what is publicly verified.
- Doctors are **controlled demonstration identities** (`DEMO_IDENTITY`) — no real
  practitioner's credentials are claimed.
- Live queues/beds/doctor slots/ambulance ETA are never fabricated; the provider
  returns `LIVE_UNAVAILABLE` and the UI renders an explicit unavailable state.
- Medical camps in the prototype are clearly labeled demo entries.
- AI summaries state their engine and are generated only from authorized records.

## Security notes

MFA for every role · PBKDF2-SHA256 hashing (device secrets, OTPs compared in constant
time) · JWT access + rotating refresh with revocation on logout · device passkey-style
unlock (hash only, **no biometric images ever stored**) · per-identity rate limiting ·
break-glass time-boxed with mandatory justification · full audit trail · secrets via
environment variables (see `.env.example`: `AUTH_SECRET`, `DATABASE_URL`, optional
`GEMINI_API_KEY` / `AI_API_KEY` for the AI engine and `GOOGLE_MAPS_API_KEY` for live
Places discovery — the app runs fully without any of them).

## Running the tests

```bash
cd backend && ../.venv/Scripts/python test_e2e.py
# → PASS 88–92 / FAIL 0 — ALL DEMO FLOWS GREEN (count varies with live
#   Overpass availability; live-provider checks skip gracefully when the
#   public API is degraded — never a fabricated result)
#   (core flows + live sync + location-aware discovery + health-memory timeline +
#    medication taken-today + location-aware camps + discover filters +
#    hospital→department→doctor→request flow + staff suggest / patient accept)
```

## Final enhancement pass

The final source includes the following improvements:

- Location-aware discovery uses a fresh device GPS fix (without repeatedly asking for permission once permission is granted).
- Find Care and appointment discovery use the same location source.
- The duplicate Hospitals navigation item is removed; Find Care is the primary healthcare discovery entry.
- The login page no longer exposes a presentation-only role selector. Every role uses the same authenticated flow.
- Emergency uses a fresh GPS fix, a prominent device `tel:108` action, the stored minimum-necessary emergency summary, voice briefing, and nearby-facility navigation. QR emergency flow is not present.
- Medical camps are future-dated and location-filtered. When Google Places is configured, public place discovery is attempted for camp-related listings; controlled demo listings remain available for an academic prototype when no live camp source is configured.
- Patient medical logs, prescriptions, medications, appointments and Health Memory remain database-backed.

See `FINAL_RUNBOOK.md` for setup and data-boundary notes.
