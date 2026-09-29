import { useCallback, useEffect, useState } from "react"
import { get, post } from "../lib/api"
import { useAuth } from "../auth"
import { useLiveReload } from "../lib/sync"
import { Card, Empty, ErrorBox, Field, Modal, PageHeader, Pill, Spinner, Stat, SuccessBox } from "../components/ui"
import type { Appointment } from "../lib/types"

export default function DoctorDashboard() {
  const { me } = useAuth() as any
  const [appts, setAppts] = useState<Appointment[] | null>(null)
  const [selected, setSelected] = useState<Appointment | null>(null)
  const [msg, setMsg] = useState("")

  const load = useCallback(async () => {
    const r = await get<{ appointments: Appointment[] }>("/appointments")
    setAppts(r.appointments)
  }, [])
  useEffect(() => { load() }, [load])
  useLiveReload(load)  // live: confirmed appointments appear without refresh

  if (!appts) return <Spinner />
  const today = new Date().toISOString().slice(0, 10)
  const upcoming = appts.filter((a) => a.status === "CONFIRMED"
    && a.appointment_date >= today).sort((a, b) => a.appointment_date.localeCompare(b.appointment_date))
  const completed = appts.filter((a) => a.status === "COMPLETED")

  return (
    <div className="space-y-6">
      <PageHeader title="Doctor Console"
        subtitle={`${me?.doctor?.name ?? ""} — ${me?.doctor?.qualification ?? ""} · ${me?.doctor?.designation ?? ""}. Your view is scoped to your speciality and scheduled patients.`} />
      {msg && <SuccessBox message={msg} />}

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Scheduled ahead" value={upcoming.length} tone="blue" />
        <Stat label="Consultations completed" value={completed.length} tone="green" />
        <Stat label="Access scope" value="Speciality-filtered" tone="slate" />
      </div>

      <section>
        <h2 className="section-title mb-3">My schedule</h2>
        {upcoming.length === 0 ? <Empty title="No scheduled patients" hint="Confirmed appointments from reception appear here." /> : (
          <div className="space-y-3">
            {upcoming.map((a) => (
              <Card key={a.id}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-bold">{a.patient_name}</p>
                    <p className="muted">{a.appointment_date} · {a.time_slot} · {a.hospital_name} · Token {a.token_number ?? "—"}</p>
                    <p className="text-xs text-ink-500">Reason: {a.reason ?? "—"}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusPill status={a.status} />
                    <button className="btn-primary" onClick={() => setSelected(a)}>Open consultation</button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      {completed.length > 0 && (
        <section>
          <h2 className="section-title mb-3">Past consultations</h2>
          <div className="space-y-2">
            {completed.slice(0, 6).map((a) => (
              <Card key={a.id} className="!py-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-bold">{a.patient_name} · {a.appointment_date}</p>
                  <p className="text-xs text-ink-500">{a.reason ?? ""}</p>
                </div>
                <button className="btn-secondary !py-1.5" onClick={() => setSelected(a)}>View snapshot</button>
              </Card>
            ))}
          </div>
        </section>
      )}

      {selected && (
        <ConsultationModal appt={selected} me={me} onClose={() => setSelected(null)}
          onDone={async (m) => { setMsg(m); setSelected(null); await load() }} />
      )}
    </div>
  )
}

function StatusPill({ status }: { status: string }) {
  const tones: Record<string, "green" | "amber" | "red" | "slate" | "blue"> = {
    CONFIRMED: "green", REQUESTED: "amber", RESCHEDULED: "amber", COMPLETED: "blue", REJECTED: "red",
  }
  return <Pill tone={tones[status] ?? "slate"}>{status.replace("_", " ")}</Pill>
}

function ConsultationModal({ appt, me, onClose, onDone }:
  { appt: Appointment; me: any; onClose: () => void; onDone: (m: string) => void }) {
  const [snap, setSnap] = useState<any | null>(null)
  const [snapErr, setSnapErr] = useState("")
  const [rxOpen, setRxOpen] = useState(false)
  const [note, setNote] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    (async () => {
      try {
        const s = await get<any>(`/clinical-snapshot/${appt.patient_id}?speciality_key=${me?.doctor?.speciality_key ?? ""}`)
        setSnap(s)
      } catch (e: any) { setSnapErr(e.message) }
    })()
  }, [appt, me])

  const complete = async () => {
    setBusy(true)
    try {
      await post(`/appointments/${appt.id}/complete`, { notes: note || "Consultation completed" })
      onDone(`Consultation completed for ${appt.patient_name}.`)
    } catch (e: any) { setSnapErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal open onClose={onClose} title={`Consultation — ${appt.patient_name}`}>
      {snapErr && <ErrorBox message={snapErr} />}
      {!snap ? <Spinner label="Preparing authorized Clinical Snapshot…" /> : (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-2 text-center text-sm">
            <div className="rounded-xl bg-slate-50 py-2"><p className="text-xs text-ink-500">Age</p><p className="font-bold">{snap.patient.age ?? "—"}</p></div>
            <div className="rounded-xl bg-slate-50 py-2"><p className="text-xs text-ink-500">Blood group</p><p className="font-bold">{snap.patient.blood_group ?? "—"}</p></div>
            <div className="rounded-xl bg-slate-50 py-2"><p className="text-xs text-ink-500">Language</p><p className="font-bold">{snap.patient.preferred_language}</p></div>
          </div>

          {snap.allergies.length > 0 && (
            <div className="rounded-xl bg-red-50 px-4 py-3">
              <p className="text-xs font-bold uppercase text-red-700">⚠️ ALLERGIES</p>
              {snap.allergies.map((a: any, i: number) => (
                <p key={i} className="text-sm font-semibold text-red-800">{a.allergen} — {a.severity}{a.reaction ? ` · ${a.reaction}` : ""}</p>
              ))}
            </div>
          )}

          <div className="rounded-xl bg-brand-50 px-4 py-3">
            <p className="text-xs font-bold uppercase text-brand-700">AI summary ({snap.ai_summary.engine === "server_side_llm" ? "model" : "built-in"}) — scope: {snap.speciality_filter ?? "all"}</p>
            <p className="mt-1 whitespace-pre-line text-sm">{snap.ai_summary.snapshot}</p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <SnapshotList title="Relevant conditions" items={snap.conditions.map((c: any) => `${c.condition} (${c.status})${c.in_scope ? "" : " · outside speciality"}`)} />
            <SnapshotList title="Current medications" items={snap.medications.map((m: any) => `${m.name} — ${m.dosage ?? ""} ${m.frequency ?? ""}`)} />
            <SnapshotList title="Relevant reports" items={snap.reports.map((r: any) => `${r.title} · ${r.report_date}`)} />
            <SnapshotList title="Recent symptoms" items={snap.recent_symptoms.map((s: any) => `${s.date}: ${s.symptoms ?? "—"} (pain ${s.pain_level ?? "—"}/10)`)} />
            <SnapshotList title="Relevant consultations" items={snap.relevant_consultations.map((c: any) => `${c.date} · ${c.doctor} · ${c.reason ?? ""}`)} />
          </div>

          <Field label="Consultation note">
            <textarea className="input min-h-20" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Findings, advice…" />
          </Field>

          <div className="flex flex-wrap gap-2">
            <button className="btn-primary flex-1" onClick={() => setRxOpen(true)}>✚ Create prescription</button>
            <button className="btn-secondary flex-1" disabled={busy} onClick={complete}>{busy ? "Saving…" : "Mark consultation complete"}</button>
          </div>
        </div>
      )}
      {rxOpen && (
        <RxForm patientId={appt.patient_id} appointmentId={appt.id} onClose={() => setRxOpen(false)}
          onDone={(m) => { setRxOpen(false); onDone(m) }} />
      )}
    </Modal>
  )
}

function SnapshotList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
      <p className="text-xs font-bold uppercase text-ink-500">{title}</p>
      {items.length === 0 ? <p className="muted">None in scope</p> : (
        <ul className="ml-4 list-disc text-sm">{items.map((it, i) => <li key={i}>{it}</li>)}</ul>
      )}
    </div>
  )
}

function RxForm({ patientId, appointmentId, onClose, onDone }:
  { patientId: number; appointmentId: number; onClose: () => void; onDone: (m: string) => void }) {
  const [diagnosis, setDiagnosis] = useState("")
  const [instructions, setInstructions] = useState("")
  const [followUp, setFollowUp] = useState("")
  const [items, setItems] = useState([{ medicine: "", dosage: "", frequency: "", duration_days: 7, instructions: "" }])
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setErr(""); setBusy(true)
    try {
      await post("/prescriptions", {
        patient_id: patientId, appointment_id: appointmentId,
        diagnosis_text: diagnosis || null, instructions: instructions || null,
        follow_up_on: followUp || null,
        items: items.filter((i) => i.medicine.trim()).map((i) => ({
          medicine: i.medicine, dosage: i.dosage || null, frequency: i.frequency || null,
          duration_days: i.duration_days || null, instructions: i.instructions || null,
        })),
      })
      onDone("Prescription issued — it is now visible to the patient (and authorized caregiver) instantly.")
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal open onClose={onClose} title="Create prescription">
      <div className="space-y-3">
        <Field label="Diagnosis / purpose"><input className="input" value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)} /></Field>
        {items.map((it, idx) => (
          <div key={idx} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <input className="input" placeholder="Medicine" value={it.medicine}
                onChange={(e) => setItems((arr) => arr.map((x, i) => i === idx ? { ...x, medicine: e.target.value } : x))} />
              <input className="input" placeholder="Dosage" value={it.dosage}
                onChange={(e) => setItems((arr) => arr.map((x, i) => i === idx ? { ...x, dosage: e.target.value } : x))} />
              <input className="input" placeholder="Frequency" value={it.frequency}
                onChange={(e) => setItems((arr) => arr.map((x, i) => i === idx ? { ...x, frequency: e.target.value } : x))} />
              <input className="input" type="number" min={1} placeholder="Duration (days)" value={it.duration_days}
                onChange={(e) => setItems((arr) => arr.map((x, i) => i === idx ? { ...x, duration_days: parseInt(e.target.value) } : x))} />
            </div>
            {items.length > 1 && (
              <button className="mt-2 text-xs font-bold text-red-600" onClick={() => setItems((arr) => arr.filter((_, i) => i !== idx))}>Remove medicine</button>
            )}
          </div>
        ))}
        <button className="btn-ghost" onClick={() => setItems((arr) => [...arr, { medicine: "", dosage: "", frequency: "", duration_days: 7, instructions: "" }])}>+ Add another medicine</button>
        <Field label="General instructions"><textarea className="input min-h-16" value={instructions} onChange={(e) => setInstructions(e.target.value)} /></Field>
        <Field label="Follow-up date (optional)"><input type="date" className="input" value={followUp} onChange={(e) => setFollowUp(e.target.value)} /></Field>
        {err && <ErrorBox message={err} />}
        <div className="flex gap-2">
          <button className="btn-secondary flex-1" onClick={onClose}>Cancel</button>
          <button className="btn-primary flex-1" disabled={busy || !items.some((i) => i.medicine.trim())} onClick={submit}>
            {busy ? "Issuing…" : "Issue prescription"}
          </button>
        </div>
      </div>
    </Modal>
  )
}
