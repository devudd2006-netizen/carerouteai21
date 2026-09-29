import { useEffect, useState } from "react"
import { get, post } from "../lib/api"
import { Card, ErrorBox, PageHeader, Pill, Spinner } from "../components/ui"
import type { Hospital, DoctorRow } from "../lib/types"
import { BookingDialog } from "./Appointments"
import { navUrl } from "../components/SimpleMap"
import { getSearchLocation, useSearchLocation } from "../lib/location"

type Step = "concern" | "speciality" | "hospital" | "doctor"

export default function FindCare() {
  const [step, setStep] = useState<Step>("concern")
  const [concern, setConcern] = useState("")
  const [urgency, setUrgency] = useState<"ROUTINE" | "URGENT" | "EMERGENCY">("ROUTINE")
  const [suggest, setSuggest] = useState<any[] | null>(null)
  const [speciality, setSpeciality] = useState<string>("")
  const [hospitals, setHospitals] = useState<(Hospital & { why?: string[] })[] | null>(null)
  const [hospital, setHospital] = useState<Hospital | null>(null)
  const [doctors, setDoctors] = useState<DoctorRow[] | null>(null)
  const [doctor, setDoctor] = useState<DoctorRow | null>(null)
  const [directHospital, setDirectHospital] = useState<Hospital | null>(null)
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)
  const [disclaimer, setDisclaimer] = useState("")
  // §9/§20: shared session location — requested once, reused across pages.
  const { loc, status, useMyLocation, searchManual } = useSearchLocation(true)
  const [manualText, setManualText] = useState("")

  // Automatically request location once on first entry; the shared session cache
  // prevents repeated permission prompts across CareRoute pages.
  useEffect(() => {
    if (!loc && status === "idle") useMyLocation().catch(() => undefined)
  }, [loc, status, useMyLocation])

  const SPECIALITIES = [
    ["orthopaedics", "🦴", "Bone & joint concerns"], ["cardiology", "❤️", "Heart & BP"],
    ["general_medicine", "🩺", "General health, fever, diabetes"], ["ophthalmology", "👁️", "Eye & vision"],
    ["urology", "💧", "Urinary & kidney"], ["ent", "👂", "Ear, nose, throat"],
    ["dermatology", "🧴", "Skin & hair"], ["obstetrics_gynaecology", "🤰", "Women's health"],
    ["oncology", "🎗️", "Cancer care"], ["emergency", "🚨", "Emergency & trauma"],
  ]

  const analyze = async () => {
    setErr(""); setBusy(true)
    try {
      let activeLoc = loc
      if (!activeLoc) {
        const ok = await useMyLocation()
        if (!ok) { setErr("Location is required for nearby care discovery. Enable location or search for an area first."); return }
        activeLoc = getSearchLocation()
      }
      const r = await post<any>("/find-care/suggest", { concern })
      setSuggest(r.suggestions)
      setDisclaimer(r.disclaimer)
      // §4: reduce user effort — if the description maps to a care category, go
      // straight to nearby capable facilities (the speciality grid stays reachable
      // via "← Change speciality" for users who prefer to pick themselves).
      if (r.suggestions?.length) {
        await pickSpeciality(r.suggestions[0].speciality_key, activeLoc ?? undefined)
      } else {
        setStep("speciality")
      }
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  const pickSpeciality = async (key: string, locationOverride?: { lat: number; lng: number }) => {
    setSpeciality(key); setBusy(true); setErr("")
    try {
      // Location-aware discovery (§9): same discover service as Hospitals.
      const q = new URLSearchParams({ speciality: key, radius_km: "25" })
      const activeLoc = locationOverride ?? loc
      if (activeLoc) { q.set("lat", String(activeLoc.lat)); q.set("lng", String(activeLoc.lng)) }
      const r = await get<{ facilities: (Hospital & { why?: string[] })[] }>(`/hospitals/discover?${q}`)
      setHospitals(r.facilities)
      setStep("hospital")
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  const pickHospital = async (h: Hospital) => {
    setHospital(h); setBusy(true); setErr("")
    try {
      // Public live-discovered hospitals may not expose a local doctor/department
      // directory. Never block the patient because that information is unavailable.
      if (!h.id || h.place_id) {
        setDoctors([])
        setStep("doctor")
        return
      }
      const r = await get<{ doctors: DoctorRow[] }>(`/doctors?speciality=${speciality}&hospital_id=${h.id}`)
      setDoctors(r.doctors)
      setStep("doctor")
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  const suggestedKeys = new Set((suggest ?? []).map((s) => s.speciality_key))

  return (
    <div className="space-y-6">
      <PageHeader title="Find Care"
        subtitle="Describe what you're facing — we help route you to the right speciality, hospital and doctor. This is care navigation, not a diagnosis." />

      {urgency === "EMERGENCY" && (
        <Card className="!border-red-300 !bg-red-50">
          <p className="font-bold text-red-700">This looks like an emergency</p>
          <p className="text-sm text-red-900/80">Major injuries, chest pain, unconsciousness, heavy bleeding — use the Emergency Center instead of booking a routine visit.</p>
          <a href="/app/emergency" className="btn-danger mt-3">🚨 Open Emergency Center</a>
        </Card>
      )}
      {err && <ErrorBox message={err} />}

      <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-ink-500">
        {(["concern", "speciality", "hospital", "doctor"] as Step[]).map((s, i) => (
          <span key={s} className={step === s ? "text-brand-700" : ""}>
            {i + 1}. {s}{i < 3 ? " →" : ""}
          </span>
        ))}
      </div>

      {step === "concern" && (
        <Card>
          {/* §9: location controls before the search */}
          <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl bg-slate-50 px-3 py-2.5">
            <span className="label !mb-0">📍 {loc ? `Near ${loc.label}` : "Your location"}</span>
            {loc && <Pill tone="blue">{loc.source === "device" ? "using current location" : "search location"}</Pill>}
            <button className="btn-secondary !py-1.5" onClick={useMyLocation}>
              {loc?.source === "device" ? "Refresh" : "Use my current location"}
            </button>
            <input className="input !w-52 !py-1.5" placeholder="or search another location"
              value={manualText} onChange={(e) => setManualText(e.target.value)} />
            <button className="btn-secondary !py-1.5" onClick={async () => {
              const ok = await searchManual(manualText)
              if (!ok) setErr(`Could not find "${manualText.trim()}". Try a city or area name.`)
              setManualText("")
            }}>Set</button>
            {status === "denied" && <span className="text-xs text-amber-700">Location not granted — nothing assumed.</span>}
          </div>
          <textarea className="input min-h-28 text-base" placeholder="Describe your concern in your own words — e.g. 'knee pain while climbing stairs for 2 weeks'"
            value={concern} onChange={(e) => setConcern(e.target.value)} />
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="label !mb-0">Urgency:</span>
            {(["ROUTINE", "URGENT", "EMERGENCY"] as const).map((u) => (
              <button key={u} onClick={() => setUrgency(u)}
                className={`rounded-xl border px-3 py-1.5 text-sm font-semibold ${urgency === u ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200"}`}>
                {u}
              </button>
            ))}
          </div>
          <button className="btn-primary mt-4" disabled={concern.trim().length < 3 || busy} onClick={analyze}>
            {busy ? "Analyzing…" : "Suggest specialities"}
          </button>
        </Card>
      )}

      {step === "speciality" && (
        <div className="space-y-4">
          {suggest && suggest.length > 0 && (
            <Card className="!bg-brand-50 !border-brand-200">
              <p className="text-sm font-bold text-brand-800">Based on your description, consider:</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {suggest.map((s) => (
                  <button key={s.speciality_key} onClick={() => pickSpeciality(s.speciality_key)}
                    className="btn-primary !py-1.5">{SPECIALITIES.find(x => x[0] === s.speciality_key)?.[1]} {SPECIALITY_LABELS[s.speciality_key] ?? s.label}</button>
                ))}
              </div>
              <p className="mt-2 text-xs text-brand-900/70">{disclaimer}</p>
            </Card>
          )}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {SPECIALITIES.map(([key, icon, label]) => (
              <button key={key} onClick={() => pickSpeciality(key)}
                className={`card p-4 text-left transition-transform hover:-translate-y-0.5 ${suggestedKeys.has(key) ? "!border-brand-400" : ""}`}>
                <div className="text-2xl">{icon}</div>
                <p className="mt-1 font-bold">{SPECIALITY_LABELS[key] ?? key}</p>
                <p className="muted">{label}</p>
                {suggestedKeys.has(key) && <Pill tone="green">suggested for you</Pill>}
              </button>
            ))}
          </div>
        </div>
      )}

      {step === "hospital" && hospitals && (
        <div className="space-y-3">
          {suggest && suggest.length > 0 && speciality === suggest[0].speciality_key && (
            <Card className="!bg-brand-50 !border-brand-200">
              <p className="font-bold text-brand-800">{SPECIALITY_LABELS[speciality] ?? speciality} care may be appropriate — based on your description.</p>
              <p className="mt-1 text-sm text-brand-900/80">Preliminary guidance — not a diagnosis. Below are nearby facilities offering this type of care.</p>
              <div className="mt-2 flex flex-wrap gap-2">
                <button className="btn-secondary" onClick={() => { window.location.href = `/app/hospitals?speciality=${speciality}` }}>🏥 Browse in Hospitals</button>
              </div>
            </Card>
          )}
          <button className="btn-ghost" onClick={() => setStep("speciality")}>← Change speciality</button>
          <h3 className="section-title">{SPECIALITY_LABELS[speciality] ?? speciality} care near you{loc ? ` — ${loc.label}` : ""}</h3>
          {hospitals.length === 0 && (
            <Card className="p-6 text-center">
              <p className="font-semibold">No facilities for this speciality were found near your location.</p>
              <p className="muted mt-1">Try a wider search or another location — or pick a different speciality.</p>
              <button className="btn-secondary mt-3" onClick={() => setStep("speciality")}>Change speciality</button>
            </Card>
          )}
          {hospitals.map((h) => (
            <Card key={h.place_id ?? h.id} className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-bold">{h.name} <span className="pill ml-1 bg-slate-100 text-slate-600">{h.hospital_type}</span></p>
                <p className="muted">{h.address || "Information unavailable"}{h.phone ? ` · ${h.phone}` : ""}</p>
                <p className="text-xs text-ink-500">
                  {h.distance_km != null ? `≈ ${h.distance_km} km away` : "distance unavailable (set location)"} ·
                  identity info publicly verified
                </p>
              </div>
              <div className="flex gap-2">
                {h.latitude != null && h.longitude != null && (
                  <a className="btn-secondary" href={navUrl(h.latitude, h.longitude, h.name, loc ? { lat: loc.lat, lng: loc.lng } : null)} target="_blank" rel="noreferrer">Get Directions</a>
                )}
                {h.phone && <a className="btn-secondary" href={`tel:${h.phone}`}>Call</a>}
                <button className="btn-secondary" onClick={() => setDirectHospital(h)}>Request here</button>
                <button className="btn-primary" onClick={() => pickHospital(h)}>View care</button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {step === "doctor" && doctors && hospital && (
        <div className="space-y-3">
          <button className="btn-ghost" onClick={() => setStep("hospital")}>← Change hospital</button>
          {doctors.length === 0 && <Card><p className="muted">No demo doctor listed for this speciality at this hospital. Try another hospital.</p></Card>}
          {doctors.map((d) => (
            <Card key={`${d.doctor_id}-${d.hospital_id}`} className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-bold">{d.name}</p>
                <p className="muted">{d.qualification} · {d.designation}</p>
                <p className="text-xs text-ink-500">OPD: {d.opd_days} · {d.consultation_hours} · {d.years_experience} yrs experience
                  · <span className="pill ml-1 bg-amber-100 text-amber-800">{d.verification_status}</span></p>
              </div>
              <button className="btn-primary" onClick={() => setDoctor(d)}>Request appointment</button>
            </Card>
          ))}
        </div>
      )}

      {doctor && hospital && <BookingDialog doctor={{ ...doctor, hospital_name: hospital.name, hospital_id: hospital.id || null, public_hospital: hospital.place_id ? hospital : null }} onClose={() => setDoctor(null)}
        onBooked={() => { setDoctor(null); alert("Request sent — track it under Appointments."); setStep("concern") }} />}
      {directHospital && <BookingDialog doctor={{ doctor_id: null, name: "Hospital Appointment Desk", hospital_name: directHospital.name, hospital_id: directHospital.id || null, public_hospital: directHospital.place_id ? directHospital : directHospital }}
        onClose={() => setDirectHospital(null)}
        onBooked={() => { setDirectHospital(null); alert("Appointment request sent to hospital reception. Track it under Appointments."); setStep("concern") }} />}
      {busy && <Spinner label="" />}
    </div>
  )
}

const SPECIALITY_LABELS: Record<string, string> = {
  orthopaedics: "Orthopaedics", cardiology: "Cardiology", general_medicine: "General Medicine",
  ophthalmology: "Ophthalmology", urology: "Urology", ent: "ENT", dermatology: "Dermatology",
  obstetrics_gynaecology: "Obstetrics & Gynaecology", oncology: "Oncology", emergency: "Emergency",
}
