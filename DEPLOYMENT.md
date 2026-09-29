# CareRoute AI — Deployment Guide

## Local preview (Windows PowerShell)

Terminal 1:
```powershell
cd frontend
npm install
npm run build
```

Terminal 2:
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

Open `http://127.0.0.1:8000` after the frontend build. The FastAPI app serves `frontend/dist` when it exists.

For Vite development instead:
```powershell
cd frontend
npm run dev
```
Then open `http://localhost:5173`. The dev frontend expects the API at `http://localhost:8000`.

## Demo accounts

| Role | ID |
|---|---|
| User / Patient | +919840000001 |
| Caregiver | +919840000002 |
| Doctor | DOC101 |
| Hospital Staff | STF201 |
| Hospital Admin | ADM001 |
| Community Health Worker | CHW042 |

Prototype OTP is intentionally returned by `/auth/request-otp` and displayed in the login UI. This is for the multi-laptop demonstration only.

## Production-style single-link deployment

Render can use `render.yaml` in this repository. The build creates the React bundle and the FastAPI server serves it from one origin.

For a real deployment:
- set `DATABASE_URL` to PostgreSQL;
- set a strong `AUTH_SECRET`;
- configure `GOOGLE_MAPS_API_KEY` only if you want Google Places;
- keep `CAREROUTE_PROVIDER=overpass` if using public OpenStreetMap discovery;
- replace prototype OTP with an SMS provider;
- connect only authorized hospital feeds for live appointments, beds, queues or doctor schedules.

CareRoute never treats the demo database as a hospital EHR and never claims that synthetic doctors or appointment slots are live hospital data.
