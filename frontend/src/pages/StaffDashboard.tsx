import { useCallback, useEffect, useState } from "react"
import { get, post } from "../lib/api"
import { useLiveReload } from "../lib/sync"
import { Card, Empty, ErrorBox, Field, Modal, PageHeader, Pill, Spinner, Stat, SuccessBox } from "../components/ui"
import type { Appointment } from "../lib/types"

export default function StaffDashboard() {
  const [appts, setAppts] = useState<Appointment[] | null>(null)
  const [me, setMe] = useState<any>(null)
  const [decide, setDecide] = useState<{ a: Appointment; kind: "confirm" | "reject" | "reschedule" } | null>(null)
  const [msg, setMsg] = useState("")
  const [err] = useState("")

  const load = useCallback(async () => {
    const [a, m] = await Promise.all([get<{ appointments: Appointment[] }>("/appointments"), get<any>("/auth/me")])
    setAppts(a.appointments)
    setMe(m)
  }, [])
  useEffect(() => { load() }, [load])
  useLiveReload(load)  // live: new requests appear without manual refresh

  if (!appts || !me) return <Spinner />
  const today = new Date().toISOString().slice(0, 10)
  const pending = appts.filter((a) => a.status === "REQUESTED" || a.status === "RESCHEDULED")
  const todayAppts = appts.filter((a) => a.appointment_date === today && a.status === "CONFIRMED")
  const confirmed = appts.filter((a) => a.status === "CONFIRMED")

  return (
    <div className="space-y-6">
      <PageHeader title="Reception Desk"
        subtitle={`${me.name} — appointment workflow for your hospital. You see appointment and patient-contact details only; clinical history is never part of your view.`} />
      {msg && <SuccessBox message={msg} />}
      {err && <ErrorBox message={err} />}

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Pending requests" value={pending.length} tone={pending.length > 0 ? "amber" : "slate"} data-testid="pending-count" />
        <Stat label="Today's confirmed" value={todayAppts.length} tone="green" />
        <Stat label="Total confirmed" value={confirmed.length} tone="blue" />
      </div>

      <section>
        <h2 className="section-title mb-3">Incoming appointment requests</h2>
        {pending.length === 0 ? <Empty title="No pending requests" hint="New requests from patients, caregivers and community workers appear here." /> : (
          <div className="space-y-3">
            {pending.map((a) => (
              <Card key={a.id}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-bold">{a.patient_name} <span className="muted">· via {a.requested_on_behalf.toLowerCase()}</span></p>
                    <p className="muted">{a.doctor_name} ({a.department ?? a.speciality_key}) · {a.hospital_name}</p>
                    <p className="text-xs text-ink-500">{a.appointment_date} · {a.time_slot} · Reason: {a.reason ?? "—"}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button className="btn-primary" onClick={() => setDecide({ a, kind: "confirm" })}>✓ Accept</button>
                    <button className="btn-secondary" onClick={() => setDecide({ a, kind: "reschedule" })}>Suggest Another Time</button>
                    <button className="btn-danger" onClick={() => setDecide({ a, kind: "reject" })}>✕ Reject</button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="section-title mb-3">Confirmed appointments</h2>
        {confirmed.length === 0 ? <Empty title="Nothing confirmed yet" /> : (
          <div className="space-y-2">
            {confirmed.map((a) => (
              <Card key={a.id} className="!py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-bold">{a.patient_name} · {a.doctor_name}</p>
                    <p className="text-xs text-ink-500">{a.appointment_date} · {a.time_slot} · Token {a.token_number ?? "—"}</p>
                  </div>
                  <Pill tone="green">{a.status}</Pill>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      {decide && (
        <DecisionModal decide={decide} onClose={() => setDecide(null)}
          onDone={async (m) => { setMsg(m); setDecide(null); await load() }} />
      )}
    </div>
  )
}

function DecisionModal({ decide, onClose, onDone }:
  { decide: { a: Appointment; kind: "confirm" | "reject" | "reschedule" }; onClose: () => void; onDone: (m: string) => void }) {
  const { a, kind } = decide
  const [note, setNote] = useState("")
  const [newDate, setNewDate] = useState("")
  const [newSlot, setNewSlot] = useState("")
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setErr(""); setBusy(true)
    try {
      if (kind === "confirm") {
        await post(`/appointments/${a.id}/confirm`, { note: note || null })
        onDone(`Appointment confirmed for ${a.patient_name} — patient and doctor dashboards updated.`)
      } else if (kind === "reject") {
        await post(`/appointments/${a.id}/reject`, { note: note || "Cannot accommodate this slot" })
        onDone(`Request rejected. ${a.patient_name} will be notified with the reason.`)
      } else {
        await post(`/appointments/${a.id}/reschedule`, { note: note || null, new_date: newDate, new_slot: newSlot })
        onDone(`Appointment moved to ${newDate} ${newSlot}. The patient is notified to confirm.`)
      }
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  const titles = { confirm: "Accept request", reject: "Reject request", reschedule: "Suggest another time" }
  return (
    <Modal open onClose={onClose} title={titles[kind]}>
      <div className="space-y-4">
        <div className="rounded-xl bg-slate-50 p-3 text-sm">
          <p><b>{a.patient_name}</b> → {a.doctor_name}</p>
          <p className="muted">{a.appointment_date} · {a.time_slot} · {a.hospital_name}</p>
        </div>
        <Field label="Note to patient (optional)">
          <input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. OPD 2, please arrive 15 min early" />
        </Field>
        {kind === "reschedule" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="New date"><input type="date" className="input" value={newDate} onChange={(e) => setNewDate(e.target.value)} /></Field>
            <Field label="New time slot"><input className="input" value={newSlot} onChange={(e) => setNewSlot(e.target.value)} placeholder="e.g. 10:00 - 10:30" /></Field>
          </div>
        )}
        {err && <ErrorBox message={err} />}
        <div className="flex gap-2">
          <button className="btn-secondary flex-1" onClick={onClose}>Cancel</button>
          <button className={`${kind === "reject" ? "btn-danger" : "btn-primary"} flex-1`} disabled={busy || (kind === "reschedule" && (!newDate || !newSlot))} onClick={submit}>
            {busy ? "Working…" : kind === "confirm" ? "Confirm" : kind === "reject" ? "Reject" : "Move appointment"}
          </button>
        </div>
      </div>
    </Modal>
  )
}
