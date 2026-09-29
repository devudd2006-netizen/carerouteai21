"""CareRoute AI — server-side AI service.

Rules enforced here:
  1. The AI only ever receives information the authorization engine has already
     filtered (callers pass pre-authorized dicts — never raw DB handles).
  2. The AI never diagnoses, prescribes, invents availability, or decides access.
  3. If no AI key is configured, a deterministic, transparent summarizer is used
     so the prototype works offline and never pretends a model ran.

Key resolution (master prompt §45): GEMINI_API_KEY (documented name) → AI_API_KEY
(generic alias). If a Gemini key is set, the Gemini API is called natively
(generateContent); otherwise an OpenAI-compatible endpoint is used when AI_API_KEY
is present (AI_BASE_URL/AI_MODEL env-overridable).
"""
import os

import httpx

AI_API_KEY = (os.environ.get("GEMINI_API_KEY") or os.environ.get("AI_API_KEY") or "").strip()
AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://api.openai.com/v1")
AI_MODEL = os.environ.get("AI_MODEL", "gpt-4o-mini")
_GEMINI_BASE = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
_IS_GEMINI = bool(os.environ.get("GEMINI_API_KEY", "").strip())

GUARDRAIL = (
    "You are CareRoute Assistant, a healthcare coordination helper. "
    "You MUST NOT diagnose, prescribe, or invent clinical facts. Summarize ONLY the "
    "provided information. If information is missing, say so. Never fabricate "
    "availability or medical data."
)


def _llm(system: str, user: str) -> str | None:
    """Calls the configured AI provider when a key exists; returns None otherwise.

    GEMINI_API_KEY → native Gemini generateContent call.
    AI_API_KEY     → OpenAI-compatible /chat/completions endpoint.
    """
    if not AI_API_KEY:
        return None
    try:
        if _IS_GEMINI:
            resp = httpx.post(
                f"{_GEMINI_BASE}/models/{_GEMINI_MODEL}:generateContent",
                headers={"x-goog-api-key": AI_API_KEY},
                json={"systemInstruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user", "parts": [{"text": user}]}],
                      "generationConfig": {"temperature": 0.2}},
                timeout=20)
            resp.raise_for_status()
            parts = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
            return "\n".join(p.get("text", "") for p in parts).strip() or None
        resp = httpx.post(
            f"{AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {AI_API_KEY}"},
            json={"model": AI_MODEL, "temperature": 0.2,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]},
            timeout=20)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return None  # graceful degradation — never fake an AI response


def _engine() -> str:
    return "server_side_llm" if AI_API_KEY else "deterministic_summarizer"


def _names(items, key: str) -> list[str]:
    """Accepts a list of dicts or plain strings and returns display names."""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            v = it.get(key) or it.get("name") or ""
            if v:
                out.append(str(v))
        elif it:
            out.append(str(it))
    return out


# ------------------------------------------------------------ summarizers
def summarize_health_memory(info: dict) -> dict:
    """info: pre-authorized {patient_name, conditions, medications, recent_logs, reports}."""
    prompt = (
        f"Summarize this person's health memory in 4-6 plain sentences for the person "
        f"themselves. Note trends in the daily logs. Do not diagnose.\n{info}")
    text = _llm(GUARDRAIL, prompt)
    if not text:
        conds = ", ".join(_names(info.get("conditions"), "condition")) or "no recorded conditions"
        meds = _names(info.get("medications"), "name")
        logs = info.get("recent_logs", [])
        trend = ""
        if logs:
            pains = [l.get("pain_level") for l in logs if l.get("pain_level") is not None]
            if pains:
                trend = f" Pain levels across the last {len(pains)} entries: {pains[0]} → {pains[-1]}."
        medtxt = f" Active medications: {', '.join(meds)}." if meds else " No active medications recorded."
        text = (f"{info.get('patient_name', 'This person')} has {conds}.{medtxt}{trend} "
                f"This is a summary of recorded information only — not a medical assessment.")
    return {"summary": text, "engine": _engine(), "ai_generated": bool(AI_API_KEY)}


def generate_clinical_snapshot(info: dict, speciality_label: str) -> dict:
    """info: speciality-filtered, authorization-approved clinical information only."""
    prompt = (
        f"Produce a concise clinical snapshot ({speciality_label}) from ONLY this "
        f"information: conditions, allergies, current medications, relevant reports, "
        f"recent symptoms. Flag allergies clearly. Do not diagnose or prescribe.\n{info}")
    text = _llm(GUARDRAIL, prompt)
    if not text:
        conds = ", ".join(_names(info.get("conditions"), "condition")) or "None recorded"
        allergies = info.get("allergies", [])
        alltxt = "; ".join(
            (f"{a['allergen']} ({a.get('severity', 'severity not recorded')})"
             if isinstance(a, dict) else str(a)) for a in allergies) or "None recorded"
        meds = _names(info.get("medications"), "name")
        reports = _names(info.get("reports"), "title")
        symptoms = info.get("recent_symptoms") or "No recent symptom entries"
        text = (
            f"CLINICAL SNAPSHOT — {speciality_label} (prototype summary)\n"
            f"• Relevant conditions: {conds}\n"
            f"• ALLERGIES: {alltxt}\n"
            f"• Current medications: {', '.join(meds) if meds else 'None recorded'}\n"
            f"• Relevant reports: {'; '.join(reports) if reports else 'None in this speciality'}\n"
            f"• Recent symptoms: {symptoms}\n"
            f"Generated from authorized records only. Not a diagnosis.")
    return {"snapshot": text, "engine": _engine(), "ai_generated": bool(AI_API_KEY)}


def prepare_emergency_voice_script(summary: dict) -> dict:
    """summary: authorized Emergency Health Summary fields only."""
    prompt = ("Write a short spoken emergency assistance message (max 60 words) using ONLY "
              "these facts. Calm, factual tone. Do not diagnose or invent anything.\n"
              + str(summary))
    text = _llm(GUARDRAIL, prompt)
    if not text:
        text = (
            "This is an emergency assistance request. "
            f"The person is {summary.get('name', 'a CareRoute user')}, "
            f"currently located at {summary.get('location_text') or 'an unreported location'}. "
            + (f"Reported situation: {summary['situation']}. " if summary.get("situation") else "")
            + (f"Known critical information: {summary['critical_info']}. " if summary.get("critical_info") else "")
            + (f"Emergency contact is {summary['emergency_contact']} "
               f"at {summary['emergency_phone']}. " if summary.get("emergency_contact") else
               "No emergency contact is on record. ")
            + "Please assist.")
    return {"voice_script": text, "engine": _engine()}


def suggest_speciality_ai(concern: str) -> dict | None:
    """AI-assisted care navigation over the fixed speciality registry. Never a diagnosis."""
    prompt = (f"A user describes: '{concern}'. From this fixed list pick up to 2 likely "
              f"relevant specialities and return JSON like "
              f'{{"suggestions":[{{"speciality_key":"orthopaedics","reason":"..."}}]}}. '
              f"List: orthopaedics, cardiology, oncology, ophthalmology, urology, "
              f"general_medicine, ent, dermatology, obstetrics_gynaecology. "
              f"This is navigation help, NOT diagnosis.")
    text = _llm(GUARDRAIL, prompt)
    return {"engine": _engine(), "note": "LLM configured"} if text else None
