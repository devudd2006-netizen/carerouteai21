import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { useAuth } from "../auth"
import { get, post, openFile } from "../lib/api"
import { useLiveReload } from "../lib/sync"
import { Card, ErrorBox, PageHeader, Pill, Spinner, SuccessBox } from "../components/ui"
import { resolvePatientId } from "./UserHome"

interface TimelineEvent { date: string; kind: string; title: string; detail: string; source: string; ref: string }

const KIND_ICON: Record<string, string> = {
  log: "📝", appointment: "📅", prescription: "📄", report: "🧪", condition: "🩺",
}

export default function HealthMemory() {
  const { me } = useAuth()
  const [data, setData] = useState<any | null>(null)
  const [err, setErr] = useState("")
  const [ok, setOk] = useState("")
  const [tab, setTab] = useState<"timeline" | "conditions" | "meds">("timeline")
  const [summary, setSummary] = useState<any | null>(null)
  const [sumBusy, setSumBusy] = useState(false)
  // condition form
  const [cond, setCond] = useState("")
  // medication form
  const [med, setMed] = useState({ name: "", dosage: "", frequency: "" })

  const load = useCallback(async () => {
    const pid = await resolvePatientId(me)
    if (!pid) return setData({ empty: true })
    const d = await get<any>(`/health-memory/${pid}`)
    setData({ pid, ...d })
  }, [me])

  useEffect(() => { load() }, [load])
  useLiveReload(load)

  if (!data) return <Spinner />
  if (data.empty) {
    return (
      <div className="space-y-6">
        <PageHeader title="Health Memory" subtitle="Your longitudinal health record, built only from your own data." />
        <Card className="p-10 text-center">
          <div className="text-4xl">🌱</div>
          <p className="mt-2 font-semibold">Your Health Memory is empty — and honestly so.</p>
          <p className="muted mx-auto mt-2 max-w-md">
            Your Health Memory will develop as you add medical logs, appointments, prescriptions
            and health records. Nothing is pre-filled: CareRoute never invents history.
          </p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            <Link to="/app/logs" className="btn-primary">📝 Add your first daily log</Link>
            <Link to="/app/medications" className="btn-secondary">💊 Add a medication</Link>
          </div>
        </Card>
      </div>
    )
  }

  const timeline: TimelineEvent[] = data.timeline ?? []
  const activeMeds = (data.medications ?? []).filter((m: any) => m.status === "ACTIVE")

  const addCondition = async () => {
    setErr(""); setOk("")
    if (!cond.trim()) return
    try {
      await post("/health-memory/conditions", { condition: cond.trim() })
      setOk("Condition added to your health memory.")
      setCond("")
      await load()
    } catch (e: any) { setErr(e.message) }
  }

  const addMed = async () => {
    setErr(""); setOk("")
    if (!med.name.trim()) return
    try {
      await post("/medications", { name: med.name.trim(), dosage: med.dosage || null, frequency: med.frequency || null })
      setOk("Medication added.")
      setMed({ name: "", dosage: "", frequency: "" })
      await load()
    } catch (e: any) { setErr(e.message) }
  }

  const summarize = async () => {
    setSumBusy(true); setErr("")
    try {
      const s = await get<any>(`/health-memory/${data.pid}/summary`)
      setSummary(s)
    } catch (e: any) { setErr(e.message) } finally { setSumBusy(false) }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Health Memory" subtitle="Everything here comes from your own records — daily logs, appointments, prescriptions, reports. Nothing is invented."
        right={<button className="btn-primary" onClick={summarize} disabled={sumBusy}>{sumBusy ? "Summarizing…" : "✨ AI summary"}</button>} />

      {summary && (
        <Card className="!bg-brand-50 !border-brand-200">
          <p className="text-xs font-bold uppercase tracking-wide text-brand-700">AI summary — {summary.engine === "server_side_llm" ? "server-side model" : "built-in summarizer"}</p>
          <p className="mt-2 whitespace-pre-line text-sm text-ink-900">{summary.summary}</p>
          <p className="mt-2 text-xs text-ink-500">Generated only from information you are allowed to see. Not a medical assessment.</p>
        </Card>
      )}

      {err && <ErrorBox message={err} />}
      {ok && <SuccessBox message={ok} />}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <div className="mb-4 flex gap-2">
              {([["timeline", "Timeline"], ["conditions", "Conditions & allergies"], ["meds", "Medications"]] as const).map(([k, label]) => (
                <button key={k} onClick={() => setTab(k)}
                  className={`rounded-xl px-3.5 py-2 text-sm font-semibold ${tab === k ? "bg-brand-600 text-white" : "bg-slate-100 text-ink-700"}`}>
                  {label}
                </button>
              ))}
            </div>

            {tab === "timeline" && (
              <div>
                {timeline.length === 0 ? (
                  <div className="text-center">
                    <p className="muted">Nothing here yet.</p>
                    <Link to="/app/logs" className="btn-primary mt-3">📝 Add your first daily log</Link>
                  </div>
                ) : (
                  <ol className="relative space-y-3 border-l-2 border-slate-100 pl-5">
                    {timeline.map((ev, i) => (
                      <li key={`${ev.ref}-${i}`} className="relative">
                        <span className="absolute -left-[31px] flex h-6 w-6 items-center justify-center rounded-full bg-white text-sm ring-2 ring-slate-100">
                          {KIND_ICON[ev.kind] ?? "•"}
                        </span>
                        <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm font-bold">{ev.title}</p>
                            <span className="text-xs font-semibold text-ink-500">{ev.date}</span>
                          </div>
                          {ev.detail && <p className="muted mt-0.5">{ev.detail}</p>}
                          <p className="mt-1 text-[11px] uppercase tracking-wide text-ink-500">source: {ev.source}</p>
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
                <p className="mt-4 text-xs text-ink-500">
                  Want to add to your history? <Link to="/app/logs" className="font-semibold text-brand-700 underline">Medical Logs</Link> ·{" "}
                  <Link to="/app/medications" className="font-semibold text-brand-700 underline">Medications</Link> · reports upload below.
                </p>
              </div>
            )}

            {tab === "conditions" && (
              <div className="space-y-4">
                {(data.conditions ?? []).length === 0 && (data.allergies ?? []).length === 0 && (
                  <p className="muted">No conditions or allergies recorded — add your own below, or they'll appear here if a doctor records one.</p>
                )}
                {(data.conditions ?? []).map((c: any) => (
                  <div key={c.id} className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                    <div className="flex items-center justify-between">
                      <p className="font-bold">{c.condition}</p>
                      <Pill tone={c.status === "ACTIVE" ? "amber" : "green"}>{c.status}</Pill>
                    </div>
                    <p className="muted mt-0.5">{c.speciality_key?.replace("_", " ")}{c.diagnosed_on ? ` · since ${c.diagnosed_on}` : ""} · {c.source === "USER_REPORTED" ? "reported by you" : "from care team (demo)"}</p>
                    {c.notes && <p className="text-xs text-ink-500">{c.notes}</p>}
                  </div>
                ))}
                {(data.allergies ?? []).map((a: any) => (
                  <div key={`al-${a.id}`} className="rounded-xl border border-red-100 bg-red-50 px-4 py-3">
                    <div className="flex items-center justify-between">
                      <p className="font-bold text-red-700">⚠️ {a.allergen}</p>
                      <Pill tone="red">{a.severity}</Pill>
                    </div>
                    {a.reaction && <p className="text-xs text-red-900/70">{a.reaction}</p>}
                  </div>
                ))}
                <div className="flex gap-2">
                  <input className="input" placeholder="Add a condition…" value={cond} onChange={(e) => setCond(e.target.value)} />
                  <button className="btn-secondary" onClick={addCondition}>Add</button>
                </div>
              </div>
            )}

            {tab === "meds" && (
              <div className="space-y-3">
                {activeMeds.length === 0 && <p className="muted">No active medications recorded.</p>}
                {activeMeds.map((m: any) => (
                  <div key={m.id} className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                    <div>
                      <p className="font-bold">{m.name}</p>
                      <p className="muted">{m.dosage} · {m.frequency}{m.prescribed_by ? ` · ${m.prescribed_by}` : ""}</p>
                    </div>
                    <Pill tone="green">ACTIVE</Pill>
                  </div>
                ))}
                <div className="rounded-2xl border border-dashed border-slate-300 p-4">
                  <p className="mb-3 text-sm font-bold">Add a medicine</p>
                  <div className="grid gap-2 sm:grid-cols-3">
                    <input className="input" placeholder="Name" value={med.name} onChange={(e) => setMed({ ...med, name: e.target.value })} />
                    <input className="input" placeholder="Dosage" value={med.dosage} onChange={(e) => setMed({ ...med, dosage: e.target.value })} />
                    <input className="input" placeholder="Frequency" value={med.frequency} onChange={(e) => setMed({ ...med, frequency: e.target.value })} />
                  </div>
                  <button className="btn-primary mt-3" onClick={addMed}>Add medicine</button>
                </div>
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <h3 className="section-title mb-2">Medical reports</h3>
            <ReportsList />
          </Card>
          <Card>
            <h3 className="section-title mb-2">Prescriptions</h3>
            <p className="muted mb-2">Latest prescriptions from your doctors.</p>
            <Link to="/app/prescriptions" className="btn-secondary w-full">Open prescriptions →</Link>
          </Card>
        </div>
      </div>
    </div>
  )
}

export function ReportsList() {
  const [reports, setReports] = useState<any[] | null>(null)
  useEffect(() => {
    (async () => {
      const r = await get<{ reports: any[] }>("/reports").catch(() => ({ reports: [] }))
      setReports(r.reports)
    })()
  }, [])
  if (!reports) return <Spinner label="" />
  if (reports.length === 0) return <p className="muted">No reports uploaded yet.</p>
  return (
    <div className="space-y-2">
      {reports.map((r) => (
        <div key={r.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2">
          <div>
            <p className="text-sm font-semibold">{r.title}</p>
            <p className="text-xs text-ink-500">{r.report_type} · {r.report_date}</p>
          </div>
          <button className="btn-ghost !py-1" onClick={() => openFile(`/reports/${r.id}/file`)}>View</button>
        </div>
      ))}
    </div>
  )
}
