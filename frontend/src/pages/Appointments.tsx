import { useCallback, useEffect, useState } from "react"

import { get, post } from "../lib/api"
import { useAuth } from "../auth"
import { useLiveReload } from "../lib/sync"
import { useSearchLocation } from "../lib/location"
import { Card, Empty, ErrorBox, Field, PageHeader, Spinner, StatusPill, SuccessBox } from "../components/ui"
import type { Appointment, Hospital, DoctorRow } from "../lib/types"
import { resolvePatientId } from "./UserHome"
import { navUrl } from "../components/SimpleMap"

export default function Appointments() {
  const [appts, setAppts] = useState<Appointment[] | null>(null)
  const [msg] = useState("")
  const [err, setErr] = useState("")
  const [discovering, setDiscovering] = useState(false)

  const load = useCallback(async () => {
    const r = await get<{ appointments: Appointment[] }>("/appointments")
    setAppts(r.appointments)
  }, [])

  const [actionMsg, setActionMsg] = useState("")
  const acceptNewTime = async (a: Appointment) => {
    try {
      await post(`/appointments/${a.id}/accept-reschedule`, {})
      setActionMsg("New time accepted — appointment confirmed.")
      await load()
    } catch (e: any) { setErr(e.message) }
  }

  useEffect(() => { load() }, [load])
  useLiveReload(load)  // live: status changes from reception appear automatically
  if (!appts) return <Spinner />

  const today = new Date().toISOString().slice(0, 10)
  const upcoming = appts.filter((a) => a.appointment_date >= today && a.status !== "REJECTED")
    .sort((a, b) => a.appointment_date.localeCompare(b.appointment_date))
  const past = appts.filter((a) => !upcoming.includes(a))

  return (
    <div className="space-y-6">
      <PageHeader title="Appointments"
        subtitle="Requests are confirmed by hospital reception. You'll get a notification at every step."
        right={<button className="btn-primary" onClick={() => setDiscovering(true)}>Request new appointment</button>} />
      {msg && <SuccessBox message={msg} />}
      {actionMsg && <SuccessBox message={actionMsg} />}
      {err && <ErrorBox message={err} />}

      <section>
        <h2 className="section-title mb-3">Upcoming</h2>
        {upcoming.length === 0 ? (
          <Empty title="No upcoming appointments" hint="Request an appointment — start from hospitals near your location."
            action={<button className="btn-primary" onClick={() => setDiscovering(true)}>Find hospitals near me</button>} />
        ) : (
          <div className="space-y-3">
            {upcoming.map((a) => (
              <div key={a.id}>
                <ApptRow a={a} />
                {a.status === "RESCHEDULED" && (
                  <div className="mt-1 mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
                    <p className="text-sm text-amber-900"><b>The hospital suggested a new time:</b> {a.appointment_date} · {a.time_slot}{a.staff_note ? ` — ${a.staff_note}` : ""}</p>
                    <button className="btn-primary !py-1.5" onClick={() => acceptNewTime(a)}>Accept new time</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {past.length > 0 && (
        <section>
          <h2 className="section-title mb-3">History</h2>
          <div className="space-y-3">
            {past.map((a) => <ApptRow key={a.id} a={a} small />)}
          </div>
        </section>
      )}

      {discovering && (
        <AppointmentDiscovery onClose={() => setDiscovering(false)}
          onBooked={() => { setDiscovering(false); load() }} />
      )}
    </div>
  )
}

/* ------------------------------------------------ §10 location-aware discovery.
   USER LOCATION → NEARBY HOSPITALS → SELECT HOSPITAL → DEPARTMENT → public doctor
   information → APPOINTMENT REQUEST (a request — never a claimed live slot). */
export function AppointmentDiscovery({ onClose, onBooked, initialHospitalId }:
  { onClose: () => void; onBooked: () => void; initialHospitalId?: number }) {
  const { loc, status, useMyLocation, searchManual } = useSearchLocation(true)
  const [manualText, setManualText] = useState("")
  const [speciality, setSpeciality] = useState("")
  const [radius, setRadius] = useState(10)
  const [hospitals, setHospitals] = useState<(Hospital & { why?: string[] })[] | null>(null)
  const [hospital, setHospital] = useState<Hospital | null>(null)
  const [deptId, setDeptId] = useState<number | null>(null)
  const [doctors, setDoctors] = useState<DoctorRow[] | null>(null)
  const [doctor, setDoctor] = useState<DoctorRow | null>(null)
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)

  const SPECIALTIES = [
    ["", "Any speciality"], ["orthopaedics", "Orthopaedics"], ["cardiology", "Cardiology"],
    ["general_medicine", "General Medicine"], ["ophthalmology", "Ophthalmology"],
    ["ent", "ENT"], ["dermatology", "Dermatology"], ["obstetrics_gynaecology", "Obstetrics & Gynaecology"],
    ["oncology", "Oncology"], ["urology", "Urology"],
  ]

  const loadHospitals = useCallback(async (opts?: { lat?: number | null; lng?: number | null; spec?: string; r?: number }) => {
    setBusy(true); setErr("")
    try {
      const p = new URLSearchParams()
      const lat = opts?.lat !== undefined ? opts.lat : loc?.lat
      const lng = opts?.lng !== undefined ? opts.lng : loc?.lng
      if (lat != null && lng != null) { p.set("lat", String(lat)); p.set("lng", String(lng)) }
      const spec = opts?.spec !== undefined ? opts.spec : speciality
      if (spec) p.set("speciality", spec)
      p.set("radius_km", String(opts?.r ?? radius))
      const r = await get<{ facilities: (Hospital & { why?: string[] })[] }>(`/hospitals/discover?${p}`)
      setHospitals(r.facilities)
      if (!initialHospitalId) { setHospital(null); setDeptId(null); setDoctors(null); setDoctor(null) }
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }, [loc, speciality, radius, initialHospitalId])

  useEffect(() => {
    // The location hook refreshes a granted device permission without prompting again.
    // If a location is already available, discovery starts immediately.
    loadHospitals()
  }, [loadHospitals])

  // Entry from HospitalDetail: load that hospital directly, preserving selection.
  useEffect(() => {
    if (initialHospitalId) {
      get<Hospital>(`/hospitals/${initialHospitalId}`).then((h) => { setHospital(h); pickHospital(h) }).catch(() => undefined)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialHospitalId])

  const pickHospital = async (h: Hospital) => {
    setHospital(h); setDeptId(null); setDoctors(null); setDoctor(null); setBusy(true); setErr("")
    try {
      if (!h.id || h.place_id) { setDoctors([]); setBusy(false); return }  // live Places rows have no local departments
      const detail = await get<Hospital>(`/hospitals/${h.id}`)
      setHospital(detail)
      setBusy(false)
    } catch (e: any) { setErr(e.message); setBusy(false) }
  }

  const pickDepartment = async (deptId: number) => {
    setDeptId(deptId); setBusy(true); setErr("")
    try {
      const q = new URLSearchParams({ hospital_id: String(hospital!.id), department_id: String(deptId) })
      const r = await get<{ doctors: DoctorRow[] }>(`/doctors?${q}`)
      setDoctors(r.doctors)
    } catch (e: any) { setDoctors([]); setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4" onClick={onClose}>
      <div className="card my-8 w-full max-w-2xl p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold">Request an appointment</h3>
          <button className="btn-secondary !px-2.5 !py-1" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {/* Step 1: location + specialty + radius → nearby hospitals */}
        {!hospital && (
          <>
            <div className="flex flex-wrap items-center gap-2 rounded-xl bg-slate-50 px-3 py-2.5">
              <span className="label !mb-0">📍 {loc ? `Near ${loc.label}` : "Your location"}</span>
              <button className="btn-secondary !py-1.5" onClick={useMyLocation}>
                {loc?.source === "device" ? "Refresh" : "Use my current location"}
              </button>
              <input className="input !w-48 !py-1.5" placeholder="or search another location"
                value={manualText} onChange={(e) => setManualText(e.target.value)}
                onKeyDown={async (e) => {
                  if (e.key === "Enter") {
                    const ok = await searchManual(manualText)
                    if (!ok) setErr(`Could not find "${manualText.trim()}".`)
                    setManualText("")
                  }
                }} />
              <button className="btn-secondary !py-1.5" onClick={async () => {
                const ok = await searchManual(manualText)
                if (!ok) setErr(`Could not find "${manualText.trim()}".`)
                setManualText("")
              }}>Set</button>
              <select className="input !w-44 !py-1.5" value={speciality}
                onChange={(e) => { setSpeciality(e.target.value); loadHospitals({ spec: e.target.value }) }}>
                {SPECIALTIES.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </select>
              {[5, 10, 25, 100].map((r) => (
                <button key={r} onClick={() => { setRadius(r); loadHospitals({ r }) }}
                  className={`rounded-xl border px-2.5 py-1.5 text-xs font-semibold ${radius === r ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200"}`}>
                  {r} km
                </button>
              ))}
              {status === "denied" && <span className="text-xs text-amber-700">Location not granted — nothing assumed.</span>}
            </div>

            {err && <div className="mt-3"><ErrorBox message={err} /></div>}

            {hospitals === null ? <Spinner label="Finding nearby hospitals…" /> : (
              <div className="mt-4 space-y-3">
                <p className="muted text-sm">Step 1 — choose a hospital near you. Requests go to that hospital's reception.</p>
                {hospitals.length === 0 ? (
                  <Card className="p-6 text-center">
                    <p className="font-semibold">No hospitals found within {radius} km for this search.</p>
                    <div className="mt-3 flex justify-center gap-2">
                      <button className="btn-primary" onClick={() => { const n = radius === 5 ? 10 : radius === 10 ? 25 : 100; setRadius(n); loadHospitals({ r: n }) }}>
                        Expand search
                      </button>
                      <button className="btn-secondary" onClick={() => loadHospitals({ spec: "" })}>Clear speciality</button>
                    </div>
                  </Card>
                ) : hospitals.map((h) => (
                  <Card key={h.place_id ?? h.id} className="flex flex-wrap items-center justify-between gap-3 !py-4">
                    <div>
                      <p className="font-bold">{h.name} {h.distance_km != null && <span className="pill ml-1 bg-slate-100 text-slate-600">≈ {h.distance_km} km</span>}</p>
                      <p className="muted">{h.address || "Information unavailable"}</p>
                      {h.departments.length > 0 && (
                        <p className="text-xs text-ink-500">{h.departments.map((d) => d.speciality_key.replace("_", " ")).slice(0, 5).join(", ")}</p>
                      )}
                    </div>
                    <div className="flex gap-2">
                      {h.latitude != null && h.longitude != null && (
                        <a className="btn-secondary" href={navUrl(h.latitude, h.longitude, h.name, loc ? { lat: loc.lat, lng: loc.lng } : null)} target="_blank" rel="noreferrer">Directions</a>
                      )}
                      <button className="btn-primary" onClick={() => pickHospital(h)}>Select</button>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </>
        )}

        {/* Step 2: hospital selected → departments (§8, only when data exists) */}
        {hospital && !deptId && (
          <div className="mt-2 border-t border-slate-100 pt-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-bold">{hospital.name} <span className="muted">— choose a department</span></p>
              <button className="btn-ghost !py-1" onClick={() => { setHospital(null); setDeptId(null); setDoctors(null) }}>← change hospital</button>
            </div>
            {hospital.departments.length === 0 ? (
              <Card className="mt-2">
                <p className="font-semibold">Department information is not available from the public hospital directory.</p>
                <p className="muted mt-1">You can still send an appointment request to this hospital. Hospital reception can assign the department and doctor after receiving the request.</p>
                <button className="btn-primary mt-3" onClick={() => setDoctor({ doctor_id: null, name: "Hospital Appointment Desk", hospital_name: hospital.name, designation: "Reception routing", verification_status: "ROUTING_ONLY" })}>Request appointment at this hospital</button>
              </Card>
            ) : (
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {hospital.departments.map((d) => (
                  <button key={d.id} onClick={() => pickDepartment(d.id)}
                    className={`card p-3 text-left transition-transform hover:-translate-y-0.5 ${deptId === d.id ? "!border-brand-400" : ""}`}>
                    <p className="font-bold text-sm">{d.name}</p>
                    <p className="muted text-xs">{d.speciality_key?.replace("_", " ")}</p>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 3: department selected → public doctor information (§9) */}
        {hospital && deptId && (
          <div className="mt-4 border-t border-slate-100 pt-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-bold">{hospital.name} <span className="muted">— {hospital.departments.find((d) => d.id === deptId)?.name ?? "department"} doctors</span></p>
              <button className="btn-ghost !py-1" onClick={() => { setDeptId(null); setDoctors(null) }}>← change department</button>
            </div>
            {doctors === null ? <Spinner label="Loading doctor information…" /> : doctors.length === 0 ? (
              <Card className="mt-2"><p className="muted">Doctor information unavailable for this department. Public doctor directories can be connected through the provider layer when available.</p></Card>
            ) : (
              <div className="mt-2 space-y-2">
                {doctors.map((d) => (
                  <Card key={`${d.doctor_id}-${d.hospital_id}`} className="flex flex-wrap items-center justify-between gap-3 !py-3">
                    <div>
                      <p className="font-bold">{d.name}</p>
                      <p className="muted">{d.qualification} · {d.designation} · {d.department_name ?? d.speciality_label ?? d.speciality_key?.replace("_", " ")}</p>
                      <p className="text-xs text-ink-500">OPD: {d.opd_days} · {d.consultation_hours} · <span className="pill bg-amber-100 text-amber-800">{d.verification_status}</span></p>
                    </div>
                    <button className="btn-primary" onClick={() => setDoctor(d)}>Request appointment</button>
                  </Card>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 4: booking dialog (a REQUEST — never a claimed live slot) */}
        {doctor && hospital && (
          <BookingDialog doctor={{ ...doctor, hospital_name: hospital.name, hospital_id: hospital.id || null, public_hospital: hospital.place_id ? hospital : null }} departmentId={deptId}
            onClose={() => setDoctor(null)}
            onBooked={() => { onBooked() }} />
        )}
        {busy && hospitals && <Spinner label="" />}
      </div>
    </div>
  )
}

function ApptRow({ a, small }: { a: Appointment; small?: boolean }) {
  return (
    <Card className={small ? "!py-3" : ""}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 flex-col items-center justify-center rounded-xl bg-brand-50 text-brand-700">
            <span className="text-sm font-black">{a.appointment_date.slice(8)}</span>
            <span className="text-[10px] font-bold uppercase">{new Date(a.appointment_date + "T00:00:00").toLocaleString("en", { month: "short" })}</span>
          </div>
          <div>
            <p className="font-bold">{a.doctor_name}</p>
            <p className="muted">{a.department ?? a.speciality_key} · {a.hospital_name}</p>
            <p className="text-xs text-ink-500">{a.appointment_date} · {a.time_slot}
              {a.token_number ? ` · Token ${a.token_number}` : ""}
              {a.requested_on_behalf !== "SELF" ? ` · booked by ${a.requested_on_behalf.toLowerCase()}` : ""}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill status={a.status} />
          {a.status === "REJECTED" && a.staff_note && <span className="text-xs text-red-600">Reason: {a.staff_note}</span>}
        </div>
      </div>
      {a.reason && !small && <p className="muted mt-2 border-t border-slate-100 pt-2">Reason: {a.reason}</p>}
    </Card>
  )
}

/** Booking dialog used by Find Care and the discovery flow after doctor selection. */
export function BookingDialog({ doctor, onClose, onBooked, departmentId }:
  { doctor: any; onClose: () => void; onBooked: (a: Appointment) => void; departmentId?: number | null }) {
  const { me } = useAuth()
  const [date, setDate] = useState("")
  const [slot, setSlot] = useState("")
  const [reason, setReason] = useState("")
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)
  const [patientId, setPatientId] = useState<number | null>(null)

  useEffect(() => {
    (async () => { setPatientId(await resolvePatientId(me)) })()
  }, [me])

  const SLOTS = ["09:00 - 09:30", "09:30 - 10:00", "10:00 - 10:30", "10:30 - 11:00",
    "11:00 - 11:30", "11:30 - 12:00", "14:00 - 14:30", "14:30 - 15:00", "15:00 - 15:30", "15:30 - 16:00"]

  const submit = async () => {
    setErr(""); setBusy(true)
    try {
      const body: any = {
        doctor_id: doctor.doctor_id ?? null,
        hospital_id: doctor.hospital_id ?? null,
        appointment_date: date, time_slot: slot, reason: reason || null,
      }
      if (departmentId) body.department_id = departmentId
      if (doctor.public_hospital) body.hospital_public = doctor.public_hospital
      if (me?.role === "CAREGIVER" && patientId) body.patient_id = patientId
      const a = await post<Appointment>("/appointments", body)
      onBooked(a)
    } catch (e: any) {
      setErr(e.message)
    } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="card w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-bold">Request appointment</h3>
        <p className="muted mb-4">{doctor.name === "Hospital Appointment Desk" ? `${doctor.hospital_name ?? "Hospital"} — reception will assign the department/doctor` : `${doctor.name} · ${doctor.hospital_name ?? "Hospital"} — ${doctor.consultation_hours ?? "OPD hours"}`}</p>
        <div className="space-y-4">
          <Field label="Date">
            <input type="date" className="input" value={date} min={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setDate(e.target.value)} />
          </Field>
          <Field label="Preferred time slot">
            <div className="grid grid-cols-2 gap-2">
              {SLOTS.map((s) => (
                <button key={s} onClick={() => setSlot(s)}
                  className={`rounded-xl border px-3 py-2 text-sm font-semibold ${slot === s ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200 bg-white"}`}>
                  {s}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Reason (optional)">
            <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. knee pain follow-up" />
          </Field>
          <p className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-ink-500">
            This sends a request to the hospital reception — they confirm, reschedule or decline.
            No live doctor calendar is connected, so slots are indicative.
          </p>
          {err && <ErrorBox message={err} />}
          <div className="flex gap-2">
            <button className="btn-secondary flex-1" onClick={onClose}>Cancel</button>
            <button className="btn-primary flex-1" disabled={!date || !slot || busy} onClick={submit}>
              {busy ? "Sending…" : "Send request"}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
