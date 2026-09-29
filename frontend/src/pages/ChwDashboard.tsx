import { useCallback, useEffect, useState } from "react"
import { get, post } from "../lib/api"
import { useLiveReload } from "../lib/sync"
import { useAuth } from "../auth"
import { Card, Empty, ErrorBox, Field, Modal, PageHeader, Pill, Spinner, Stat, SuccessBox } from "../components/ui"

export default function ChwDashboard() {
  const { me } = useAuth() as any
  const [assigned, setAssigned] = useState<any[] | null>(null)
  const [visits, setVisits] = useState<any[] | null>(null)
  const [appts, setAppts] = useState<any[] | null>(null)
  const [msg, setMsg] = useState("")
  const [visitFor, setVisitFor] = useState<any | null>(null)
  const [apptFor, setApptFor] = useState<any | null>(null)

  const load = useCallback(async () => {
    const [a, v, ap] = await Promise.all([
      get<{ assigned: any[] }>("/community-care/assigned"),
      get<{ visits: any[] }>("/community-care/visits"),
      get<{ appointments: any[] }>("/appointments"),
    ])
    setAssigned(a.assigned); setVisits(v.visits); setAppts(ap.appointments)
  }, [])
  useEffect(() => { load() }, [load])
  useLiveReload(load)  // live: follow-up tasks and appointments stay current

  if (!assigned || !visits || !appts) return <Spinner />
  const dueCount = assigned.filter((u) => u.wellness_follow_up_required).length

  return (
    <div className="space-y-6">
      <PageHeader title="Community Care Console"
        subtitle={`${me?.name ?? ""} — authorized community health worker. Inactivity raises a wellness follow-up, never an automatic emergency.`} />
      {msg && <SuccessBox message={msg} />}

      <div className="grid gap-4 sm:grid-cols-4">
        <Stat label="Assigned users" value={assigned.length} tone="blue" />
        <Stat label="Wellness follow-ups due" value={dueCount} tone={dueCount ? "amber" : "slate"} />
        <Stat label="Visits recorded" value={visits.length} tone="green" />
        <Stat label="Appointment assistance" value={appts.length} tone="slate" />
      </div>

      <section>
        <h2 className="section-title mb-3">Assigned users</h2>
        {assigned.length === 0 ? <Empty title="No assigned users" /> : (
          <div className="grid gap-4 lg:grid-cols-2">
            {assigned.map((u) => (
              <Card key={u.patient_id} className={u.wellness_follow_up_required ? "!border-amber-300" : ""}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-bold">{u.name} <span className="muted">· {u.age ?? "?"} yrs · {u.preferred_language}</span></p>
                    <p className="muted">{u.location_text}</p>
                  </div>
                  <Pill tone={u.wellness_follow_up_required ? "amber" : "green"}>{u.priority}</Pill>
                </div>
                {u.wellness_follow_up_required && (
                  <p className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800">
                    ⏳ {u.days_since_last_activity == null ? "No recorded activity" : `No activity for ${u.days_since_last_activity} days`} → wellness follow-up required. Verify the actual situation during a visit.
                  </p>
                )}
                <p className="mt-2 text-xs text-ink-500">Last visit: {u.last_visit ?? "none recorded"}</p>
                {u.recent_appointments.length > 0 && (
                  <div className="mt-2 border-t border-slate-100 pt-2">
                    <p className="text-xs font-bold uppercase text-ink-500">Appointments</p>
                    {u.recent_appointments.map((a: any, i: number) => (
                      <p key={i} className="text-xs text-ink-500">{a.date} · {a.doctor} · {a.hospital}</p>
                    ))}
                  </div>
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  <button className="btn-primary !py-2" onClick={() => setVisitFor(u)}>Record wellness visit</button>
                  <button className="btn-secondary !py-2" onClick={() => setApptFor(u)}>Request appointment</button>
                  <a className="btn-secondary !py-2" href={`tel:${u.emergency_phone ?? ""}`}>📞 Call family</a>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h3 className="section-title mb-3">Recent visits</h3>
          {visits.length === 0 ? <p className="muted">No visits recorded yet.</p> : visits.map((v) => (
            <div key={v.id} className="border-b border-slate-100 py-2 last:border-0">
              <div className="flex items-center justify-between">
                <p className="text-sm font-bold">{v.patient_name} · {v.visit_date}</p>
                <Pill tone={v.escalation_flag ? "red" : v.wellness_status === "WELL" ? "green" : "amber"}>
                  {v.escalation_flag ? "ESCALATED" : v.wellness_status}
                </Pill>
              </div>
              {v.observations && <p className="muted">{v.observations}</p>}
            </div>
          ))}
        </Card>
        <Card>
          <h3 className="section-title mb-3">Appointment assistance</h3>
          {appts.length === 0 ? <p className="muted">No appointments yet.</p> : appts.slice(0, 8).map((a) => (
            <div key={a.id} className="flex items-center justify-between border-b border-slate-100 py-2 text-sm last:border-0">
              <span>{a.patient_name} → {a.doctor_name} · {a.appointment_date}</span>
              <Pill tone={a.status === "CONFIRMED" ? "green" : a.status === "REQUESTED" ? "amber" : "slate"}>{a.status}</Pill>
            </div>
          ))}
        </Card>
      </div>

      {visitFor && <VisitModal user={visitFor} onClose={() => setVisitFor(null)}
        onDone={async (m) => { setMsg(m); setVisitFor(null); await load() }} />}
      {apptFor && <ChwApptModal user={apptFor} onClose={() => setApptFor(null)}
        onDone={async (m) => { setMsg(m); setApptFor(null); await load() }} />}
    </div>
  )
}

function VisitModal({ user, onClose, onDone }: { user: any; onClose: () => void; onDone: (m: string) => void }) {
  const [status, setStatus] = useState("WELL")
  const [observations, setObservations] = useState("")
  const [escalate, setEscalate] = useState(false)
  const [followUp, setFollowUp] = useState("")
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setErr(""); setBusy(true)
    try {
      await post("/community-care/visit", {
        patient_id: user.patient_id, wellness_status: status,
        observations: observations || null, escalation_flag: escalate,
        follow_up_on: followUp || null,
      })
      onDone(`Visit recorded for ${user.name}.${escalate ? " Escalation flagged for the care team." : ""}`)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal open onClose={onClose} title={`Wellness visit — ${user.name}`}>
      <div className="space-y-3">
        <Field label="Wellness status">
          <div className="flex gap-2">
            {["WELL", "NEEDS_ATTENTION", "UNREACHABLE"].map((s) => (
              <button key={s} onClick={() => setStatus(s)}
                className={`flex-1 rounded-xl border px-3 py-2 text-sm font-semibold ${status === s ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200"}`}>
                {s.replace("_", " ")}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Observations"><textarea className="input min-h-24" value={observations} onChange={(e) => setObservations(e.target.value)} placeholder="How is the user doing? Medication adherence? Mobility?" /></Field>
        <label className="flex items-center gap-3 rounded-xl border border-red-100 bg-red-50 px-3 py-2">
          <input type="checkbox" checked={escalate} onChange={(e) => setEscalate(e.target.checked)} />
          <span className="text-sm text-red-700">Escalate concern to the care team (only after verifying the situation)</span>
        </label>
        <Field label="Next follow-up (optional)"><input type="date" className="input" value={followUp} onChange={(e) => setFollowUp(e.target.value)} /></Field>
        {err && <ErrorBox message={err} />}
        <div className="flex gap-2">
          <button className="btn-secondary flex-1" onClick={onClose}>Cancel</button>
          <button className="btn-primary flex-1" disabled={busy} onClick={submit}>{busy ? "Saving…" : "Record visit"}</button>
        </div>
      </div>
    </Modal>
  )
}

function ChwApptModal({ user, onClose, onDone }: { user: any; onClose: () => void; onDone: (m: string) => void }) {
  const [doctorId, setDoctorId] = useState<number | null>(null)
  const [date, setDate] = useState("")
  const [slot, setSlot] = useState("10:00 - 10:30")
  const [reason, setReason] = useState("Assisted by community health worker")
  const [doctors, setDoctors] = useState<any[] | null>(null)
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    get<{ doctors: any[] }>("/doctors").then((r) => setDoctors(r.doctors))
  }, [])

  const submit = async () => {
    setErr(""); setBusy(true)
    try {
      await post("/appointments", { patient_id: user.patient_id, doctor_id: doctorId, appointment_date: date, time_slot: slot, reason })
      onDone(`Appointment requested for ${user.name}. The hospital will confirm; inform the user afterwards.`)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal open onClose={onClose} title={`Request appointment — ${user.name}`}>
      <div className="space-y-3">
        <Field label="Doctor">
          <select className="input" value={doctorId ?? ""} onChange={(e) => setDoctorId(parseInt(e.target.value))}>
            <option value="" disabled>Select a doctor…</option>
            {(doctors ?? []).map((d) => (
              <option key={`${d.doctor_id}-${d.hospital_id}`} value={d.doctor_id}>
                {d.name} · {d.speciality_label ?? d.speciality_key} · {d.hospital_name}
              </option>
            ))}
          </select>
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Date"><input type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
          <Field label="Time slot"><input className="input" value={slot} onChange={(e) => setSlot(e.target.value)} /></Field>
        </div>
        <Field label="Reason"><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        {err && <ErrorBox message={err} />}
        <div className="flex gap-2">
          <button className="btn-secondary flex-1" onClick={onClose}>Cancel</button>
          <button className="btn-primary flex-1" disabled={!doctorId || !date || busy} onClick={submit}>{busy ? "Sending…" : "Send request"}</button>
        </div>
      </div>
    </Modal>
  )
}
