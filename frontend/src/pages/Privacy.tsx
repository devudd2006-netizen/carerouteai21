import { useCallback, useEffect, useState } from "react"
import { useAuth } from "../auth"
import { get, post } from "../lib/api"
import { useLiveReload } from "../lib/sync"
import { Card, PageHeader, Pill, Spinner } from "../components/ui"

export default function Privacy() {
  const { me } = useAuth()
  const [data, setData] = useState<any | null>(null)
  const [audit, setAudit] = useState<any[] | null>(null)
  const [enrollMsg, setEnrollMsg] = useState("")

  const load = useCallback(async () => {
    const p = await get<any>("/privacy/overview").catch(() => null)
    setData(p)
    const a = await get<{ audit: any[] }>("/audit").catch(() => ({ audit: [] }))
    setAudit(a.audit)
  }, [])

  useEffect(() => { load() }, [load])
  useLiveReload(load)  // live: access history updates as others (try to) access

  if (!audit) return <Spinner />

  const enrollDevice = async () => {
    const r = await post<any>("/auth/device/enroll", { device_name: "This browser" })
    setEnrollMsg(`Device enrolled. One-time secret (store it now): ${r.device_secret}`)
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Privacy & Permissions"
        subtitle="Who can access your information, when it was used, and full control to revoke — in plain language." />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h3 className="section-title mb-3">Who can access my information</h3>
          <div className="space-y-3 text-sm">
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <p className="font-bold">You</p>
              <p className="muted">Full access to your own Health Memory, always.</p>
            </div>
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <p className="font-bold">Caregivers you authorize</p>
              <p className="muted">{data?.who_has_access?.active_caregivers ?? 0} active. They see only the sections you explicitly granted, and you can revoke instantly.</p>
            </div>
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <p className="font-bold">Doctors</p>
              <p className="muted">{data?.who_has_access?.doctors_with_record_access ?? 0} doctor(s) have had authorized access — only when you have an appointment with them, and only speciality-relevant information. {data?.who_has_access?.note ?? ""}</p>
            </div>
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <p className="font-bold">Hospital staff</p>
              <p className="muted">Appointment workflow details only — never your clinical history.</p>
            </div>
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <p className="font-bold">Community health worker</p>
              <p className="muted">Assigned community-care information: appointments, medications, visits.</p>
            </div>
            <div className="rounded-xl bg-red-50 px-4 py-3">
              <p className="font-bold text-red-700">Break-glass emergency access</p>
              <p className="text-red-900/80">{data?.break_glass_events?.length
                ? `${data.break_glass_events.length} recorded event(s), most recent: ${String(data.break_glass_events[0].requested_at).slice(0, 16).replace("T", " ")} — ${data.break_glass_events[0].reason}`
                : "No break-glass events. If a professional ever uses emergency access, it appears here with their reason."}</p>
            </div>
          </div>
        </Card>

        <Card className="h-fit">
          <h3 className="section-title mb-3">Account security</h3>
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span>MFA (OTP) sign-in</span><Pill tone="green">Always on</Pill>
            </div>
            <div className="flex items-center justify-between">
              <span>Device passkey-style unlock</span>
              <Pill tone={me?.device_unlock_enabled ? "green" : "slate"}>{me?.device_unlock_enabled ? "Enrolled" : "Optional"}</Pill>
            </div>
            <button className="btn-secondary w-full" onClick={enrollDevice}>Enroll this device</button>
            {enrollMsg && <p className="rounded-xl bg-brand-50 p-3 text-xs break-all">{enrollMsg}</p>}
            <p className="text-xs text-ink-500">No fingerprints or face images are ever stored — device unlock uses a device-bound secret; the server keeps only a hash.</p>
            <div className="border-t border-slate-100 pt-2">
              <p className="text-xs font-bold uppercase text-ink-500">Session</p>
              <p className="muted">Sessions expire automatically; sign-out revokes the refresh token immediately.</p>
            </div>
          </div>
        </Card>
      </div>

      <Card>
        <h3 className="section-title mb-3">Access history (audit)</h3>
        {audit.length === 0 ? <p className="muted">No access recorded yet.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase text-ink-500">
                <th className="py-2">When</th><th className="py-2">Action</th><th className="py-2">By role</th><th className="py-2">Result</th><th className="py-2">Purpose</th>
              </tr></thead>
              <tbody>
                {audit.slice(0, 30).map((a) => (
                  <tr key={a.id} className="border-t border-slate-100">
                    <td className="py-2 whitespace-nowrap">{String(a.at).slice(0, 16).replace("T", " ")}</td>
                    <td className="py-2 font-semibold">{a.action.replace(/_/g, " ")}</td>
                    <td className="py-2">{a.actor_role}</td>
                    <td className="py-2">{a.result === "ALLOWED" ? <Pill tone="green">allowed</Pill> : <Pill tone="red">denied</Pill>}</td>
                    <td className="py-2 text-ink-500">{a.purpose ?? a.detail ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-xs text-ink-500">Every view of your Clinical Snapshot, prescriptions, reports and every denied attempt is permanently recorded.</p>
      </Card>
    </div>
  )
}
