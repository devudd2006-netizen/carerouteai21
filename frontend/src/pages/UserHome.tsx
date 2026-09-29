import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { useAuth } from "../auth"
import { get } from "../lib/api"
import { useLiveReload } from "../lib/sync"
import { Card, StatusPill, Spinner, PageHeader } from "../components/ui"
import type { Appointment, Notification, Me } from "../lib/types"

/** Resolve the patient record this account can see (own patient, or authorized for caregivers). */
export async function resolvePatientId(me: Me | null): Promise<number | null> {
  if (!me) return null
  if (me.patient_id) return me.patient_id
  if (me.role === "CAREGIVER") {
    const r = await get<{ patients: { patient_id: number; permissions: string[]; status: string }[] }>(
      "/caregivers/my-patients").catch(() => null)
    const active = r?.patients.find((p) => p.status === "ACTIVE")
    return active?.patient_id ?? null
  }
  return null
}

export default function UserHome() {
  const { me } = useAuth()
  const [appts, setAppts] = useState<Appointment[] | null>(null)
  const [notes, setNotes] = useState<Notification[]>([])

  const load = useCallback(async () => {
    const a = await get<{ appointments: Appointment[] }>("/appointments")
    setAppts(a.appointments)
    const n = await get<{ notifications: Notification[] }>("/notifications")
    setNotes(n.notifications)
  }, [])

  useEffect(() => { load() }, [load])
  useLiveReload(load)  // live: confirmations and prescriptions appear automatically

  if (!appts) return <Spinner />
  const today = new Date().toISOString().slice(0, 10)
  const upcoming = appts.filter((a) => ["REQUESTED", "CONFIRMED", "RESCHEDULED"].includes(a.status)
    && a.appointment_date >= today)

  return (
    <div className="space-y-8">
      <PageHeader
        title={`Vanakkam, ${me?.name.split(" ")[0]} 👋`}
        subtitle="One care journey across every hospital — remember, understand, navigate and coordinate."
        right={<Link to="/app/find-care" className="btn-primary">Find Care</Link>} />

      <Card className="overflow-hidden !border-brand-200 bg-gradient-to-br from-white via-brand-50 to-white">
        <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.18em] text-brand-700">Today’s health check</p>
            <h2 className="mt-1 text-2xl font-black tracking-tight">How are you feeling today?</h2>
            <p className="muted mt-1 max-w-xl">A quick daily log helps CareRoute understand your current situation and keep your Health Memory grounded in what you actually record.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {[['😊','Good'],['🙂','Okay'],['😟','Not well'],['🚨','Severe']].map(([icon,label]) => (
              <Link key={label} to="/app/logs" className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-center shadow-sm transition hover:-translate-y-0.5 hover:border-brand-300">
                <span className="block text-xl">{icon}</span><span className="text-xs font-bold">{label}</span>
              </Link>
            ))}
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="!border-red-200 !bg-red-50">
          <h3 className="font-bold text-red-700">🚨 Emergency</h3>
          <p className="mt-1 text-sm text-red-900/80">Immediate help with your emergency health summary, voice assistance and the nearest emergency-capable hospital.</p>
          <Link to="/app/emergency" className="btn-danger mt-3 w-full">Open Emergency Center</Link>
        </Card>
        <Card className="lg:col-span-2">
          <div className="flex items-center justify-between">
            <h3 className="section-title">Upcoming appointments</h3>
            <Link to="/app/appointments" className="btn-ghost !py-1">All appointments →</Link>
          </div>
          {upcoming.length === 0 ? (
            <p className="muted mt-3">No upcoming visits. Use Find Care to request one.</p>
          ) : (
            <div className="mt-3 space-y-2">
              {upcoming.slice(0, 3).map((a) => (
                <div key={a.id} className="flex flex-wrap items-center justify-between rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                  <div>
                    <p className="text-sm font-bold">{a.doctor_name} <span className="font-normal text-ink-500">· {a.department ?? a.speciality_key}</span></p>
                    <p className="text-xs text-ink-500">{a.hospital_name} · {a.appointment_date} · {a.time_slot}</p>
                  </div>
                  <StatusPill status={a.status} />
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card><h3 className="section-title">Current medications</h3><MedPreview /></Card>
        <Card><h3 className="section-title">Recent health log</h3><LogPreview /></Card>
        <Card>
          <h3 className="section-title">Notifications</h3>
          {notes.length === 0 ? <p className="muted mt-2">Nothing new.</p> : (
            <div className="mt-2 space-y-2">
              {notes.slice(0, 4).map((n) => (
                <div key={n.id} className="rounded-xl bg-slate-50 px-3 py-2">
                  <p className="text-sm font-semibold">{n.title}</p>
                  <p className="text-xs text-ink-500 line-clamp-2">{n.body}</p>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { to: "/app/find-care", icon: "🧭", label: "Find Care", desc: "Describe your need, then discover nearby care" },
          { to: "/app/hospitals", icon: "🏥", label: "Hospitals", desc: "Nearby care, verified info & navigation" },
          { to: "/app/camps", icon: "⛺", label: "Medical Camps", desc: "Free community camps" },
          { to: "/app/privacy", icon: "🔒", label: "Privacy Center", desc: "Who sees what" },
        ].map((q) => (
          <Link key={q.to} to={q.to} className="card p-5 transition-transform hover:-translate-y-0.5 hover:shadow-md">
            <div className="text-2xl">{q.icon}</div>
            <p className="mt-2 font-bold">{q.label}</p>
            <p className="muted">{q.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}

function MedPreview() {
  const { me } = useAuth()
  const [meds, setMeds] = useState<any[] | null>(null)
  useEffect(() => {
    (async () => {
      const pid = await resolvePatientId(me)
      if (!pid) return setMeds([])
      const hm = await get<any>(`/health-memory/${pid}`).catch(() => null)
      setMeds((hm?.medications ?? []).filter((m: any) => m.status === "ACTIVE"))
    })()
  }, [me])
  if (!meds) return <Spinner label="" />
  if (meds.length === 0) return <p className="muted mt-2">No active medicines recorded.</p>
  return (
    <div className="mt-2 space-y-2">
      {meds.slice(0, 4).map((m) => (
        <div key={m.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2">
          <span className="text-sm font-semibold">{m.name}</span>
          <span className="text-xs text-ink-500">{m.frequency}</span>
        </div>
      ))}
    </div>
  )
}

function LogPreview() {
  const { me } = useAuth()
  const [logs, setLogs] = useState<any[] | null>(null)
  useEffect(() => {
    (async () => {
      const pid = await resolvePatientId(me)
      if (!pid) return setLogs([])
      const hm = await get<any>(`/health-memory/${pid}`).catch(() => null)
      setLogs(hm?.health_logs ?? [])
    })()
  }, [me])
  if (!logs) return <Spinner label="" />
  if (logs.length === 0) return <p className="muted mt-2">No daily log yet today — <Link className="text-brand-700 underline" to="/app/memory">add one</Link>.</p>
  const latest = logs[0]
  return (
    <div className="mt-2">
      <p className="text-sm"><b>{latest.pain_level}/10</b> pain · {latest.mood ?? "—"} · {String(latest.logged_at).slice(0, 10)}</p>
      <p className="muted mt-1">{latest.symptoms ?? "No symptoms noted"}</p>
    </div>
  )
}
