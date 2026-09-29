# CareRoute AI — Final Runbook

## What is now enforced
- Existing architecture is preserved; this is an enhancement, not a rebuild.
- User navigation uses a single Find Care experience; the duplicate Hospitals menu item is removed.
- Device location is requested once and refreshed without re-prompting when permission is already granted.
- Nearby discovery is location-driven and never silently defaults to Chennai/Madurai or another fixed city.
- Medical logs are persistent patient-reported records and Health Memory is derived from stored records.
- Appointments are real CareRoute workflow records: user/caregiver/CHW request → hospital staff confirmation → doctor visibility.
- Emergency has a prominent `tel:108` action, fresh GPS capture, minimum-necessary emergency summary, AI voice briefing, and nearby facility navigation. No QR emergency flow exists.
- Medical camps are future-dated and location-filtered. With a Google Places key, live public place discovery is attempted; otherwise controlled prototype listings are used honestly.
- No raw biometric images are stored.

## Run locally
### Backend
```bash
cd backend
python -m pip install -r requirements.txt
python seed.py
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE=http://localhost:8000` for local development if needed.

## Optional live public hospital discovery
Set `GOOGLE_MAPS_API_KEY` in the backend environment. Without it, CareRoute uses keyless OpenStreetMap/Overpass nearby healthcare discovery.

## Important data boundary
Public facility discovery is not the same as access to a hospital's private patient/EHR system. Private clinical data remains inside CareRoute's authorized database/integrations. Doctor identities in the controlled demo directory are synthetic and must not be represented as real practitioners.
