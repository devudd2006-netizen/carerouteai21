import { useCallback, useEffect, useState } from "react"
import { useAuth } from "../auth"
import { get, post } from "../lib/api"
import { useLiveReload } from "../lib/sync"
import { Card, Empty, PageHeader, Pill, Spinner } from "../components/ui"
import { resolvePatientId } from "./UserHome"

interface Med { id: number; name: string; dosage: string | null; frequency: string | null; start_date: string | null; end_date: string | null; status: string; prescribed_by: string | null }

export default function MedicationsPage() {
  const { me } = useAuth()
  const [meds, setMeds] = useState<Med[] | null>(null)
  const [name, setName] = useState("")
  const [dosage, setDosage] = useState("")
  const [frequency, setFrequency] = useState("")
  const [canEdit, setCanEdit] = useState(false)

  const load = useCallback(async () => {
    const pid = await resolvePatientId(me)
    if (!pid) return setMeds([])
    const d = await get<any>(`/health-memory/${pid}`).catch(() => null)
    setMeds(d?.medications ?? [])
  }, [me])

  useEffect(() => { load() }, [load])
  useLiveReload(load)
  useEffect(() => { setCanEdit(me?.role === "USER") }, [me])

  if (!meds) return <Spinner />
  const active = meds.filter((m) => m.status === "ACTIVE")
  const past = meds.filter((m) => m.status !== "ACTIVE")

  const add = async () => {
    if (!name.trim()) return
    await post("/medications", { name: name.trim(), dosage: dosage || null, frequency: frequency || null })
    setName(""); setDosage(""); setFrequency("")
    await load()
  }

  const mark = async (id: number, status: string) => {
    await api_patch(id, status)
    await load()
  }

  const takenToday = async (id: number) => {
    await post(`/medications/${id}/taken`)
    await load()
  }

  const today = new Date().toISOString().slice(0, 10)

  const api_patch = async (id: number, status: string) => {
    const { api } = await import("../lib/api")
    await api(`/medications/${id}`, { method: "PATCH", body: JSON.stringify({ status }) })
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Medications" subtitle="Your ongoing medication routine — dosage, frequency and whether today's dose is recorded." />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-2">
          {active.length === 0 && <Empty title="No active medications" hint="Add your current medicines below or complete onboarding data." />}
          {active.map((m: any) => (
            <Card key={m.id} className="flex flex-wrap items-center justify-between !py-4">
              <div>
                <p className="font-bold">{m.name}</p>
                <p className="muted">{m.dosage} · {m.frequency}</p>
                <p className="text-xs text-ink-500">Since {m.start_date}{m.prescribed_by ? ` · ${m.prescribed_by}` : ""}</p>
              </div>
              <div className="flex items-center gap-2">
                {m.last_taken_on === today
                  ? <Pill tone="green">✓ taken today</Pill>
                  : <Pill tone="amber">not recorded today</Pill>}
                {canEdit && m.last_taken_on !== today
                  && <button className="btn-primary !py-1.5" onClick={() => takenToday(m.id)}>Mark taken today</button>}
                {canEdit && <button className="btn-secondary !py-1.5" onClick={() => mark(m.id, "COMPLETED")}>Mark ended</button>}
              </div>
            </Card>
          ))}
          {past.length > 0 && (
            <Card>
              <h3 className="section-title mb-2">Ended / paused</h3>
              {past.map((m) => (
                <div key={m.id} className="flex items-center justify-between border-b border-slate-100 py-2 last:border-0">
                  <span>{m.name} <span className="muted">· {m.frequency}</span></span>
                  <Pill tone="slate">{m.status}</Pill>
                </div>
              ))}
            </Card>
          )}
        </div>
        {canEdit && (
          <Card className="h-fit">
            <h3 className="section-title mb-3">Add a medicine</h3>
            <div className="space-y-3">
              <input className="input" placeholder="Medicine name" value={name} onChange={(e) => setName(e.target.value)} />
              <input className="input" placeholder="Dosage (e.g. 500mg, 1 tablet)" value={dosage} onChange={(e) => setDosage(e.target.value)} />
              <input className="input" placeholder="Frequency (e.g. twice daily)" value={frequency} onChange={(e) => setFrequency(e.target.value)} />
              <button className="btn-primary w-full" disabled={!name.trim()} onClick={add}>Add medicine</button>
              <p className="text-xs text-ink-500">Prescription medicines added by your doctor appear automatically after a consultation.</p>
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}
