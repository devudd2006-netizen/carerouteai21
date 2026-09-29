import { useCallback, useEffect, useState } from "react"
import { useAuth } from "../auth"
import { get, post } from "../lib/api"
import { useLiveReload } from "../lib/sync"
import { Card, ErrorBox, Field, PageHeader, Pill, Spinner, SuccessBox } from "../components/ui"
import { resolvePatientId } from "./UserHome"

interface LogRow {
  id: number; logged_at: string; pain_level: number | null; temperature_c: number | null
  mood: string | null; symptoms: string | null; adherence: string | null; notes: string | null
}

function Sparkline({ logs }: { logs: LogRow[] }) {
  const pts = [...logs].reverse().filter((l) => l.pain_level != null)
  if (pts.length < 2) return null
  const W = 480, H = 80
  const coords = pts.map((p, i) => `${(i / (pts.length - 1)) * W},${H - ((p.pain_level ?? 0) / 10) * H}`).join(" ")
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-20 w-full">
        <polyline points={coords} fill="none" stroke="#0e8178" strokeWidth="2.5" strokeLinejoin="round" />
      </svg>
      <p className="text-xs text-ink-500">Pain trend across your last {pts.length} logs</p>
    </div>
  )
}

export default function MedicalLogs() {
  const { me } = useAuth()
  const [logs, setLogs] = useState<LogRow[] | null>(null)
  const [err, setErr] = useState("")
  const [ok, setOk] = useState("")
  const [pain, setPain] = useState(3)
  const [mood, setMood] = useState("Good")
  const [symptoms, setSymptoms] = useState("")
  const [checked, setChecked] = useState<string[]>([])
  const [notes, setNotes] = useState("")
  const [temp, setTemp] = useState("")
  const [adherence, setAdherence] = useState("TAKEN_ALL")
  const [bp, setBp] = useState("")
  const [sugar, setSugar] = useState("")

  const load = useCallback(async () => {
    const id = await resolvePatientId(me)
    if (!id) return setLogs([])
    try {
      const d = await get<any>(`/health-memory/${id}`)
      setLogs(d.health_logs ?? [])
    } catch (e: any) { setErr(e.message); setLogs([]) }
  }, [me])

  useEffect(() => { load() }, [load])
  useLiveReload(load)

  if (!logs) return <Spinner />

  const today = new Date().toISOString().slice(0, 10)
  const todays = logs.find((l) => String(l.logged_at).slice(0, 10) === today)
  const previous = logs.filter((l) => l !== todays)

  const save = async () => {
    setErr(""); setOk("")
    try {
      const extra = [bp && `BP ${bp} mmHg`, sugar && `Blood sugar ${sugar} mg/dL`].filter(Boolean).join(" · ")
      await post("/health-memory/logs", {
        pain_level: pain, temperature_c: temp ? parseFloat(temp) : null,
        mood,        symptoms: [checked.join(", "), symptoms, extra].filter(Boolean).join(" · ") || null,
        notes: notes || null, adherence,
      })
      setOk("Today's log saved to your Health Memory.")
      setSymptoms(""); setNotes(""); setTemp(""); setBp(""); setSugar(""); setChecked([])
      await load()
    } catch (e: any) { setErr(e.message) }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Medical Logs"
        subtitle="Record how you feel each day. Your logs stay private and build your Health Memory over time." />

      {err && <ErrorBox message={err} />}
      {ok && <SuccessBox message={ok} />}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {/* TODAY'S LOG */}
          <Card>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="section-title !mb-0">Today's log</h3>
              {todays && <Pill tone="green">logged today</Pill>}
            </div>
            {todays ? (
              <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 px-4 py-3">
                <p className="text-sm font-bold">{String(todays.logged_at).slice(0, 10)} · pain {todays.pain_level ?? "—"}/10</p>
                <p className="muted mt-1">{todays.symptoms ?? "No symptoms recorded"}{todays.mood ? ` · feeling ${todays.mood.toLowerCase()}` : ""}</p>
                {todays.notes && <p className="text-xs text-ink-500">{todays.notes}</p>}
                <p className="mt-2 text-xs text-ink-500">You can still add another entry below — every entry is kept.</p>
              </div>
            ) : (
              <p className="muted">You haven't logged today yet. It takes under a minute.</p>
            )}

            <div className="mt-4 rounded-2xl border border-dashed border-slate-300 p-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label={`Pain level: ${pain}/10`}>
                  <input type="range" min={0} max={10} value={pain} onChange={(e) => setPain(parseInt(e.target.value))} className="w-full" />
                </Field>
                <Field label="Mood / general condition">
                  <select className="input" value={mood} onChange={(e) => setMood(e.target.value)}>
                    {["Good", "Okay", "Tired", "Unwell"].map((m) => <option key={m}>{m}</option>)}
                  </select>
                </Field>
                <Field label="Symptoms — select any that apply">
                  <div className="flex flex-wrap gap-2">
                    {["Fever", "Headache", "Dizziness", "Chest discomfort", "Breathlessness", "Nausea", "Swelling"].map((s) => {
                      const on = checked.includes(s)
                      return (
                        <button type="button" key={s}
                          onClick={() => setChecked(on ? checked.filter((x) => x !== s) : [...checked, s])}
                          className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${on ? "border-teal-600 bg-teal-50 text-teal-800" : "border-slate-300 bg-white text-ink-600 hover:border-slate-400"}`}>
                          {on ? "✓ " : ""}{s}
                        </button>
                      )
                    })}
                  </div>
                  <input className="input mt-2" value={symptoms} onChange={(e) => setSymptoms(e.target.value)} placeholder="Other symptoms or details (optional)" />
                </Field>
                <Field label="Medicines today">
                  <select className="input" value={adherence} onChange={(e) => setAdherence(e.target.value)}>
                    <option value="TAKEN_ALL">All taken</option>
                    <option value="PARTIAL">Some taken / some missed</option>
                    <option value="MISSED">Not taken</option>
                  </select>
                </Field>
                <Field label="Temperature °C (optional)">
                  <input className="input" value={temp} onChange={(e) => setTemp(e.target.value)} placeholder="36.8" />
                </Field>
                <Field label="Blood pressure (optional)">
                  <input className="input" value={bp} onChange={(e) => setBp(e.target.value)} placeholder="120/80" />
                </Field>
                <Field label="Blood sugar (optional)">
                  <input className="input" value={sugar} onChange={(e) => setSugar(e.target.value)} placeholder="110" />
                </Field>
                <Field label="Notes (optional)">
                  <input className="input" value={notes} onChange={(e) => setNotes(e.target.value)} />
                </Field>
              </div>
              <button className="btn-primary mt-4" onClick={save}>Save today's log</button>
            </div>
          </Card>

          {/* TREND */}
          {logs.length > 1 && (
            <Card>
              <h3 className="section-title mb-3">Trend</h3>
              <Sparkline logs={logs} />
            </Card>
          )}

          {/* PREVIOUS LOGS */}
          <Card>
            <h3 className="section-title mb-3">Previous logs</h3>
            {previous.length === 0 ? (
              <p className="muted">No previous logs yet.</p>
            ) : (
              <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
                {previous.map((l) => (
                  <div key={l.id} className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-bold">{String(l.logged_at).slice(0, 10)} · pain {l.pain_level ?? "—"}/10</p>
                      <Pill tone={l.adherence === "TAKEN_ALL" ? "green" : l.adherence === "MISSED" ? "red" : "amber"}>
                        {l.adherence === "TAKEN_ALL" ? "medicines taken" : l.adherence === "MISSED" ? "medicines missed" : "partial"}
                      </Pill>
                    </div>
                    <p className="muted mt-1">{l.symptoms ?? "—"}{l.mood ? ` · feeling ${l.mood.toLowerCase()}` : ""}</p>
                    {l.notes && <p className="text-xs text-ink-500">{l.notes}</p>}
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <h3 className="section-title mb-2">How this works</h3>
            <p className="muted text-sm">Each log is a private, patient-reported entry. Doctors only see
              relevant log information through the authorized Clinical Snapshot — never your whole
              history by default.</p>
            <p className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-xs text-ink-500">
              Missing a few days is completely fine — CareRoute never treats inactivity as an
              emergency. Community follow-up is only a wellness check, never an automatic ambulance call.
            </p>
          </Card>
        </div>
      </div>
    </div>
  )
}
