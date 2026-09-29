import { useCallback, useEffect, useState } from "react"
import { get } from "../lib/api"
import { useLiveReload } from "../lib/sync"
import { Card, Empty, PageHeader, Pill, Spinner } from "../components/ui"

interface RxItem { medicine: string; dosage: string | null; frequency: string | null; duration_days: number | null; instructions: string | null }
interface Rx { id: number; issued_at: string; doctor_name: string; qualification: string | null; hospital_name: string; diagnosis_text: string | null; instructions: string | null; follow_up_on: string | null; items: RxItem[] }

export default function Prescriptions() {
  const [rxs, setRxs] = useState<Rx[] | null>(null)

  const load = useCallback(async () => {
    const r = await get<{ prescriptions: Rx[] }>("/prescriptions").catch(() => ({ prescriptions: [] }))
    setRxs(r.prescriptions)
  }, [])

  useEffect(() => { load() }, [load])
  useLiveReload(load)  // live: new prescriptions appear automatically

  if (!rxs) return <Spinner />

  return (
    <div className="space-y-6">
      <PageHeader title="Prescriptions" subtitle="Every prescription is issued by a verified demo doctor at a specific hospital and belongs to your record." />
      {rxs.length === 0 && <Empty title="No prescriptions yet" hint="After a consultation, your doctor's prescription appears here." />}
      <div className="space-y-4">
        {rxs.map((rx) => (
          <Card key={rx.id}>
            <div className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-100 pb-3">
              <div>
                <p className="font-bold">{rx.doctor_name}</p>
                <p className="muted">{rx.qualification} · {rx.hospital_name}</p>
              </div>
              <div className="text-right">
                <Pill tone="blue">{String(rx.issued_at).slice(0, 10)}</Pill>
                {rx.follow_up_on && <p className="mt-1 text-xs text-ink-500">Follow-up: {rx.follow_up_on}</p>}
              </div>
            </div>
            {rx.diagnosis_text && <p className="mt-3 text-sm"><b>For:</b> {rx.diagnosis_text}</p>}
            <table className="mt-3 w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-ink-500">
                  <th className="py-1">Medicine</th><th className="py-1">Dosage</th><th className="py-1">Frequency</th><th className="py-1">Duration</th>
                </tr>
              </thead>
              <tbody>
                {rx.items.map((it, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="py-2 font-semibold">{it.medicine}</td>
                    <td className="py-2">{it.dosage}</td>
                    <td className="py-2">{it.frequency}</td>
                    <td className="py-2">{it.duration_days ? `${it.duration_days} days` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rx.instructions && <p className="mt-3 rounded-xl bg-brand-50 px-4 py-3 text-sm text-brand-900"><b>Instructions:</b> {rx.instructions}</p>}
          </Card>
        ))}
      </div>
    </div>
  )
}
