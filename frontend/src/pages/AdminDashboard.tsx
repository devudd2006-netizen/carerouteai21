import { useCallback, useEffect, useState } from "react"
import { get, post } from "../lib/api"
import { useLiveReload } from "../lib/sync"
import { Card, ErrorBox, Field, Modal, PageHeader, Pill, Spinner, Stat, SuccessBox } from "../components/ui"

export default function AdminDashboard() {
  const [data, setData] = useState<any | null>(null)
  const [sources, setSources] = useState<any | null>(null)
  const [audit, setAudit] = useState<any[]>([])
  const [msg, setMsg] = useState("")
  const [err] = useState("")
  const [addStaff, setAddStaff] = useState(false)
  const [addDept, setAddDept] = useState(false)

  const load = useCallback(async () => {
    const [o, s, a] = await Promise.all([
      get<any>("/admin/overview"),
      get<any>("/admin/data-sources"),
      get<{ audit: any[] }>("/audit"),
    ])
    setData(o); setSources(s); setAudit(a.audit)
  }, [])
  useEffect(() => { load() }, [load])
  useLiveReload(load)  // live: appointment stats stay current

  if (!data || !sources) return <Spinner />
  const h = data.hospital
  const stats = data.appointment_stats

  return (
    <div className="space-y-6">
      <PageHeader title="Hospital Administration"
        subtitle="Strongest-protection area: hospital profile, authorized staff, departments and integration status. All clinical access remains out of administrative scope." />
      {msg && <SuccessBox message={msg} />}
      {err && <ErrorBox message={err} />}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Departments" value={data.departments.length} tone="blue" />
        <Stat label="Doctors" value={data.doctors.length} tone="green" />
        <Stat label="Authorized staff" value={data.staff.length} tone="slate" />
        <Stat label="Pending appointments" value={stats["REQUESTED"] ?? 0} tone="amber" />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <h3 className="section-title mb-2">Hospital profile</h3>
          <p className="font-bold">{h.name}</p>
          <p className="muted">{h.address}, {h.city} — {h.phone}</p>
          <p className="mt-2"><Pill tone="green">Identity: publicly verified</Pill></p>
          <p className="mt-1 text-xs text-ink-500">Emergency: {h.emergency_phone} · {h.website}</p>
        </Card>

        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="section-title">Departments</h3>
            <button className="btn-ghost !py-1" onClick={() => setAddDept(true)}>+ Add</button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {data.departments.map((d: any) => (
              <span key={d.id} className="pill bg-slate-100 text-slate-700">{d.name}</span>
            ))}
          </div>
          <h3 className="section-title mb-2 mt-4">Doctors</h3>
          {data.doctors.map((d: any) => (
            <div key={d.doctor_id} className="flex items-center justify-between border-b border-slate-100 py-1.5 text-sm last:border-0">
              <span>{d.name} <span className="muted">· {d.speciality_key}</span></span>
              <Pill tone="amber">{d.verification}</Pill>
            </div>
          ))}
        </Card>

        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="section-title">Authorized staff</h3>
            <button className="btn-ghost !py-1" onClick={() => setAddStaff(true)}>+ Add</button>
          </div>
          {data.staff.map((s: any) => (
            <div key={s.staff_id} className="border-b border-slate-100 py-1.5 text-sm last:border-0">
              <p className="font-semibold">{s.designation} <span className="muted">· {s.department}</span></p>
            </div>
          ))}
          <p className="mt-2 text-xs text-ink-500">Staff sign in with their Staff ID + OTP (MFA). No passwords are stored.</p>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h3 className="section-title mb-3">Appointment workflow</h3>
          <div className="grid grid-cols-5 gap-2 text-center">
            {["REQUESTED", "CONFIRMED", "COMPLETED", "RESCHEDULED", "REJECTED"].map((k) => (
              <div key={k} className="rounded-xl bg-slate-50 py-3">
                <p className="text-xl font-black">{stats[k] ?? 0}</p>
                <p className="text-[10px] font-bold uppercase text-ink-500">{k}</p>
              </div>
            ))}
          </div>
          <h3 className="section-title mb-2 mt-4">Integration & data sources</h3>
          {sources.data_sources.map((d: any) => (
            <div key={d.id} className="flex items-center justify-between border-b border-slate-100 py-2 text-sm last:border-0">
              <div>
                <p className="font-semibold">{d.name}</p>
                <p className="text-xs text-ink-500">{d.scope}</p>
              </div>
              <Pill tone={d.status === "CONNECTED" ? "green" : d.status === "PLANNED" ? "blue" : "slate"}>{d.status}</Pill>
            </div>
          ))}
          <p className="mt-2 text-xs text-ink-500">Active provider: <b>{sources.active_provider.provider}</b> ({sources.active_provider.mode}). Authorized FHIR-based integration slots in behind the same interface when available.</p>
        </Card>

        <Card>
          <h3 className="section-title mb-3">Audit log (hospital scope)</h3>
          <div className="max-h-80 space-y-1.5 overflow-y-auto pr-1">
            {audit.slice(0, 40).map((a) => (
              <div key={a.id} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-1.5 text-xs">
                <span><b>{a.action.replace(/_/g, " ")}</b> · {a.actor_role}</span>
                <span className={a.result === "ALLOWED" ? "text-emerald-700" : "text-red-600"}>{a.result}</span>
              </div>
            ))}
            {audit.length === 0 && <p className="muted">No audit entries yet.</p>}
          </div>
        </Card>
      </div>

      {addStaff && (
        <AddStaffModal onClose={() => setAddStaff(false)} onDone={async (m) => { setMsg(m); setAddStaff(false); await load() }} />
      )}
      {addDept && (
        <AddDeptModal onClose={() => setAddDept(false)} onDone={async (m) => { setMsg(m); setAddDept(false); await load() }} />
      )}
    </div>
  )
}

function AddStaffModal({ onClose, onDone }: { onClose: () => void; onDone: (m: string) => void }) {
  const [name, setName] = useState("")
  const [designation, setDesignation] = useState("Receptionist")
  const [department, setDepartment] = useState("OPD Front Desk")
  const [out, setOut] = useState<any | null>(null)
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setErr(""); setBusy(true)
    try {
      const r = await post<any>("/admin/staff", { name, designation, department })
      setOut(r)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal open onClose={onClose} title="Add authorized staff">
      {out ? (
        <div className="space-y-3">
          <SuccessBox message={`Staff account created. Staff ID: ${out.worker_id}`} />
          <p className="text-sm">{out.note}</p>
          <button className="btn-primary w-full" onClick={() => onDone(`Staff ${out.worker_id} created`)}>Done</button>
        </div>
      ) : (
        <div className="space-y-3">
          <Field label="Full name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Designation">
            <select className="input" value={designation} onChange={(e) => setDesignation(e.target.value)}>
              {["Receptionist", "OPD Staff", "Support Staff"].map((d) => <option key={d}>{d}</option>)}
            </select>
          </Field>
          <Field label="Department"><input className="input" value={department} onChange={(e) => setDepartment(e.target.value)} /></Field>
          {err && <ErrorBox message={err} />}
          <div className="flex gap-2">
            <button className="btn-secondary flex-1" onClick={onClose}>Cancel</button>
            <button className="btn-primary flex-1" disabled={!name || busy} onClick={submit}>{busy ? "Creating…" : "Create account"}</button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function AddDeptModal({ onClose, onDone }: { onClose: () => void; onDone: (m: string) => void }) {
  const [name, setName] = useState("")
  const [key, setKey] = useState("general_medicine")
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)
  const KEYS = ["orthopaedics", "cardiology", "general_medicine", "ophthalmology", "urology", "ent",
    "dermatology", "obstetrics_gynaecology", "oncology", "emergency"]

  const submit = async () => {
    setErr(""); setBusy(true)
    try {
      await post("/admin/departments", { name, speciality_key: key })
      onDone(`Department ${name} added.`)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal open onClose={onClose} title="Add department">
      <div className="space-y-3">
        <Field label="Department name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Speciality key">
          <select className="input" value={key} onChange={(e) => setKey(e.target.value)}>
            {KEYS.map((k) => <option key={k}>{k}</option>)}
          </select>
        </Field>
        {err && <ErrorBox message={err} />}
        <div className="flex gap-2">
          <button className="btn-secondary flex-1" onClick={onClose}>Cancel</button>
          <button className="btn-primary flex-1" disabled={!name || busy} onClick={submit}>Add department</button>
        </div>
      </div>
    </Modal>
  )
}
