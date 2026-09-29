import { useState } from "react"
import { useAuth } from "../auth"
import { get, post } from "../lib/api"
import { Card, ErrorBox, Field, PageHeader, Spinner, SuccessBox, Unavailable } from "../components/ui"
import { navUrl } from "../components/SimpleMap"

export default function EmergencyPage() {
  const { me } = useAuth()
  const [stage, setStage] = useState<"idle" | "active">("idle")
  const [situation, setSituation] = useState("")
  const [loc, setLoc] = useState<{ lat: number; lng: number; accuracy_m?: number | null } | null>(null)
  const [locState, setLocState] = useState<"none" | "capturing" | "ok" | "denied">("none")
  const [locNote, setLocNote] = useState("")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState("")
  const [event, setEvent] = useState<any | null>(null)
  const [voice, setVoice] = useState<any | null>(null)
  const [resolvedMsg, setResolvedMsg] = useState("")

  const captureLocation = () => {
    setLocState("capturing"); setLocNote("")
    if (!navigator.geolocation) return setLocState("denied")
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const acc = pos.coords.accuracy != null ? Math.round(pos.coords.accuracy) : null
        setLoc({ lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy_m: acc })
        setLocNote(acc != null ? `Location accuracy: approximately ${acc} metres` : "")
        setLocState("ok")
      },
      () => setLocState("denied"), { timeout: 15000, maximumAge: 0, enableHighAccuracy: true })
  }

  const trigger = async () => {
    setErr(""); setBusy(true)
    try {
      const body: any = { situation: situation || null }
      if (loc) { body.latitude = loc.lat; body.longitude = loc.lng }
      if (me?.role === "CAREGIVER" && me.patient_id) body.patient_id = me.patient_id
      const ev = await post<any>("/emergency/trigger", body)
      setEvent(ev)
      setStage("active")
      get<any>(`/emergency/${ev.event_id}/voice-script`).then(setVoice).catch(() => null)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  const resolve = async () => {
    await post(`/emergency/${event.event_id}/resolve`)
    setResolvedMsg("Emergency marked resolved. The event remains fully visible in your audit history.")
  }

  const speak = () => {
    if (!voice?.voice_script || !("speechSynthesis" in window)) return
    const utter = new SpeechSynthesisUtterance(voice.voice_script)
    utter.rate = 0.95
    window.speechSynthesis.speak(utter)
  }

  /** Honest 108 action (§29): real tel: action where supported, never "connected". */
  const call108 = () => {
    window.location.href = "tel:108"
    setTimeout(() => {
      setResolvedMsg("Calling is not supported on this device. Please dial 108 immediately.")
    }, 1200)
  }

  if (stage === "idle") {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <PageHeader title="Emergency Center" subtitle="Activating an emergency does not require any daily log. Your minimum-necessary Emergency Health Summary is prepared instantly." />

        {/* §29: prominent CALL 108 — always available, even before activation */}
        <button className="btn-danger w-full !py-6 text-xl font-black tracking-wide"
          onClick={call108} aria-label="Call 108 emergency services">
          📞 CALL 108
        </button>
        <p className="-mt-3 text-center text-xs text-ink-500">
          For life-threatening emergencies call 108 immediately. CareRoute does not replace official
          emergency services and never claims a call is connected unless your device confirms it.
        </p>

        <Card className="!border-red-200">
          <h3 className="font-bold text-red-700">🚨 Activate emergency assistance</h3>
          <div className="mt-4 space-y-4">
            <Field label="What is happening? (optional)" hint="Short plain words, e.g. 'fell, cannot stand' or 'chest discomfort'. Leave blank if unable to type.">
              <textarea className="input min-h-20" value={situation} onChange={(e) => setSituation(e.target.value)} />
            </Field>
            <div className="rounded-xl border border-slate-200 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-bold">Location</p>
                  <p className="muted">
                    {locState === "ok" && loc ? `Captured: ${loc.lat.toFixed(4)}, ${loc.lng.toFixed(4)}` :
                      locState === "capturing" ? "Capturing…" :
                      locState === "denied" ? "Location access was not granted — nearby facility routing will not guess your location." : "Capture for accurate hospital routing."}
                  </p>
                  {locState === "ok" && locNote && (
                    <p className="text-xs text-ink-500">📍 Current location detected — {locNote}</p>
                  )}
                </div>
                <button className="btn-secondary" onClick={captureLocation} disabled={locState === "capturing"}>
                  {locState === "ok" ? "Refresh location" : "📍 Use my location"}
                </button>
              </div>
            </div>
            {err && <ErrorBox message={err} />}
            <button className="btn-danger w-full !py-4 text-base" disabled={busy} onClick={trigger}>
              {busy ? "Preparing…" : "🚨 Confirm & activate emergency"}
            </button>
            <p className="text-xs text-ink-500">
              CareRoute prepares the emergency summary and can open your device's 108 call action.
              Nearby facility routing uses only the current location captured for this emergency —
              no official 108 / ambulance integration exists, so services are never dispatched by CareRoute.
            </p>
          </div>
        </Card>
      </div>
    )
  }

  const s = event.summary
  return (
    <div className="space-y-6">
      <PageHeader title="Emergency active" subtitle="Share this page with responders or the hospital. Everything shown is the minimum necessary information." />
      {resolvedMsg && <SuccessBox message={resolvedMsg} />}

      {/* §29: CALL 108 remains prominent during an active emergency */}
      <button className="btn-danger w-full !py-6 text-xl font-black tracking-wide" onClick={call108}
        aria-label="Call 108 emergency services">📞 CALL 108</button>
      <p className="-mt-3 text-center text-xs text-ink-500">
        CareRoute never claims a 108 call is connected — your device handles the actual call.
      </p>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h3 className="section-title mb-3">Emergency Health Summary</h3>
          <div className="grid gap-3 sm:grid-cols-2 text-sm">
            <SummaryRow label="Name" value={s.name} />
            <SummaryRow label="Blood group" value={s.blood_group ?? "not recorded"} />
            <SummaryRow label="Emergency contact" value={s.emergency_contact ? `${s.emergency_contact} · ${s.emergency_phone}` : "not recorded"} />
            <SummaryRow label="Location" value={s.location_text ?? "not recorded"} />
          </div>
          <div className="mt-3 space-y-2">
            <div className="rounded-xl bg-red-50 px-4 py-3">
              <p className="text-xs font-bold uppercase text-red-700">⚠️ Allergies</p>
              <p className="text-sm">{s.allergies.length ? s.allergies.map((a: any) => `${a.allergen} (${a.severity})`).join(", ") : "None recorded"}</p>
            </div>
            <div className="rounded-xl bg-amber-50 px-4 py-3">
              <p className="text-xs font-bold uppercase text-amber-700">Critical conditions</p>
              <p className="text-sm">{s.critical_conditions.length ? s.critical_conditions.join(", ") : "None recorded"}</p>
            </div>
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <p className="text-xs font-bold uppercase text-ink-500">Important medications</p>
              <p className="text-sm">{s.important_medications.length ? s.important_medications.join(", ") : "None recorded"}</p>
            </div>
            {s.situation_reported_by_user && (
              <div className="rounded-xl bg-red-50 px-4 py-3">
                <p className="text-xs font-bold uppercase text-red-700">Reported situation</p>
                <p className="text-sm">{s.situation_reported_by_user}</p>
              </div>
            )}
          </div>
        </Card>

        <div className="space-y-6">
          <Card>
            <h3 className="section-title mb-2">🔊 AI-assisted emergency voice briefing</h3>
            {!voice ? <Spinner label="Preparing voice script…" /> : (
              <>
                <p className="rounded-xl bg-slate-50 p-3 text-sm italic">"{voice.voice_script}"</p>
                <button className="btn-primary mt-3 w-full" onClick={speak}>▶ Play voice briefing</button>
                <p className="mt-2 text-xs text-ink-500">Uses your device's speech engine. Contains only authorized summary facts. Not sent to 108 automatically.</p>
              </>
            )}
          </Card>
          <button className="btn-secondary w-full" onClick={resolve}>Mark emergency resolved</button>
        </div>
      </div>

      <Card>
        <h3 className="section-title mb-1">Nearby emergency-capable facilities</h3>
        <div className="mb-3"><Unavailable label="Ambulance live status unavailable" why="no official emergency-services integration — no ETA is invented." /></div>
        {event.facilities_note && (
          <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {event.facilities_note}
          </div>
        )}
        {(!event.facilities || event.facilities.length === 0) && !event.facilities_note && (
          <p className="muted">No emergency-capable facilities were found near the captured location.</p>
        )}
        <div className="space-y-2">
          {(event.facilities ?? []).map((f: any) => (
            <div key={`${f.data_source}-${f.hospital_id ?? f.name}`} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
              <div>
                <p className="font-bold">{f.name}</p>
                <p className="muted">{f.address}{f.distance_km != null ? ` · ≈ ${f.distance_km} km` : ""}</p>
                {!f.emergency_phone_verified && f.phone && (
                  <p className="text-xs text-ink-500">Emergency capability not verified — confirm by phone.</p>
                )}
              </div>
              <div className="flex gap-2">
                <a className="btn-secondary" href={navUrl(f.latitude, f.longitude, f.name, loc ? { lat: loc.lat, lng: loc.lng } : null)} target="_blank" rel="noreferrer">🧭 Navigate</a>
                {f.phone && <a className="btn-danger" href={`tel:${f.phone}`}>📞 {f.phone}</a>}
              </div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-ink-500">If this is life-threatening, call your local emergency number (India: 108) directly — CareRoute does not replace official emergency services.</p>
      </Card>
    </div>
  )
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 px-4 py-3">
      <p className="text-xs font-bold uppercase text-ink-500">{label}</p>
      <p className="font-semibold">{value}</p>
    </div>
  )
}
