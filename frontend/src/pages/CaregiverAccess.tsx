import { useCallback, useEffect, useState } from "react"
import { get, post, put } from "../lib/api"
import { useLiveReload } from "../lib/sync"
import { Card, ErrorBox, Field, Modal, PageHeader, Pill, Spinner, SuccessBox } from "../components/ui"
import { CAREGIVER_PERMS } from "../lib/types"
import type { Caregiver } from "../lib/types"

export default function CaregiverAccess() {
  const [caregivers, setCaregivers] = useState<Caregiver[] | null>(null)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [editing, setEditing] = useState<Caregiver | null>(null)
  const [msg, setMsg] = useState("")

  const load = useCallback(async () => {
    const r = await get<{ caregivers: Caregiver[] }>("/caregivers")
    setCaregivers(r.caregivers)
  }, [])
  useEffect(() => { load() }, [load])
  useLiveReload(load)  // live: caregiver grants/revocations stay current

  if (!caregivers) return <Spinner />

  return (
    <div className="space-y-6">
      <PageHeader title="Caregiver Access"
        subtitle="Family members see only what you explicitly allow — relationship alone grants nothing. Every use of access is recorded."
        right={<button className="btn-primary" onClick={() => setInviteOpen(true)}>+ Grant caregiver access</button>} />
      {msg && <SuccessBox message={msg} />}

      {caregivers.length === 0 ? (
        <Card><p className="muted">No caregivers have access yet.</p></Card>
      ) : caregivers.map((c) => (
        <Card key={c.relationship_id}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-bold">{c.caregiver_name} <span className="muted">· {c.relationship}</span></p>
              <p className="muted">{c.caregiver_phone}</p>
            </div>
            <div className="flex items-center gap-2">
              <Pill tone={c.status === "ACTIVE" ? "green" : "red"}>{c.status}</Pill>
              <button className="btn-secondary !py-1.5" onClick={() => setEditing(c)}>Modify permissions</button>
              {c.status === "ACTIVE" && (
                <button className="btn-danger !py-1.5" onClick={async () => {
                  await post(`/caregivers/${c.relationship_id}/revoke`)
                  setMsg(`Access revoked for ${c.caregiver_name}. They can no longer see any information.`)
                  await load()
                }}>Revoke all</button>
              )}
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {CAREGIVER_PERMS.map((p) => (
              <span key={p.key} className={`pill ${c.permissions?.[p.key] ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-400 line-through"}`}>
                {c.permissions?.[p.key] ? "✓" : "✕"} {p.label}
              </span>
            ))}
          </div>
          {c.recent_access?.length > 0 && (
            <div className="mt-3 border-t border-slate-100 pt-2">
              <p className="text-xs font-bold uppercase text-ink-500">Recent access</p>
              {c.recent_access.map((u, i) => (
                <p key={i} className="text-xs text-ink-500">{String(u.at).slice(0, 16).replace("T", " ")} — {u.action.replace(/_/g, " ").toLowerCase()} ({u.result.toLowerCase()})</p>
              ))}
            </div>
          )}
        </Card>
      ))}

      <InviteModal open={inviteOpen} onClose={() => setInviteOpen(false)} onDone={async (m) => { setMsg(m); await load() }} />
      {editing && (
        <EditModal c={editing} onClose={() => setEditing(null)} onDone={async (m) => { setMsg(m); await load() }} />
      )}
    </div>
  )
}

function InviteModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: (m: string) => void }) {
  const [name, setName] = useState("")
  const [phone, setPhone] = useState("+91")
  const [relationship, setRelationship] = useState("Son")
  const [perms, setPerms] = useState<string[]>(["view_appointments", "assist_navigation"])
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setErr(""); setBusy(true)
    try {
      await post("/caregivers/invite", { caregiver_name: name, caregiver_phone: phone.trim(), relationship, permissions: perms })
      onDone(`${name} now has the selected permissions. They sign in with phone ${phone} (create account via OTP).`)
      onClose()
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="Grant caregiver access">
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Caregiver name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Phone (they use to sign in)"><input className="input" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91…" /></Field>
        </div>
        <Field label="Relationship to you">
          <select className="input" value={relationship} onChange={(e) => setRelationship(e.target.value)}>
            {["Spouse", "Parent", "Son", "Daughter", "Sibling", "Relative", "Friend", "Caregiver", "Other"].map((r) => <option key={r}>{r}</option>)}
          </select>
        </Field>
        <div>
          <p className="label">What may they see and do?</p>
          <div className="space-y-1.5">
            {CAREGIVER_PERMS.map((p) => (
              <label key={p.key} className="flex items-center gap-3 rounded-xl border border-slate-100 px-3 py-2">
                <input type="checkbox" checked={perms.includes(p.key)}
                  onChange={(e) => setPerms((cur) => e.target.checked ? [...cur, p.key] : cur.filter((x) => x !== p.key))} />
                <span className="text-sm">{p.label}</span>
              </label>
            ))}
          </div>
          <p className="mt-2 text-xs text-ink-500">Never granted by default: full medical history, unrelated specialist records, sensitive reports, private clinical notes.</p>
        </div>
        {err && <ErrorBox message={err} />}
        <div className="flex gap-2">
          <button className="btn-secondary flex-1" onClick={onClose}>Cancel</button>
          <button className="btn-primary flex-1" disabled={!name || phone.length < 6 || busy} onClick={submit}>{busy ? "Saving…" : "Grant access"}</button>
        </div>
      </div>
    </Modal>
  )
}

function EditModal({ c, onClose, onDone }: { c: Caregiver; onClose: () => void; onDone: (m: string) => void }) {
  const [perms, setPerms] = useState<string[]>(
    Object.entries(c.permissions ?? {}).filter(([, v]) => v).map(([k]) => k))
  const [busy, setBusy] = useState(false)

  const save = async () => {
    setBusy(true)
    await put(`/caregivers/${c.relationship_id}/permissions`, { permissions: perms })
    onDone(`Permissions updated for ${c.caregiver_name}.`)
    onClose()
  }

  return (
    <Modal open onClose={onClose} title={`Permissions — ${c.caregiver_name}`}>
      <div className="space-y-3">
        {CAREGIVER_PERMS.map((p) => (
          <label key={p.key} className="flex items-center gap-3 rounded-xl border border-slate-100 px-3 py-2">
            <input type="checkbox" checked={perms.includes(p.key)}
              onChange={(e) => setPerms((cur) => e.target.checked ? [...cur, p.key] : cur.filter((x) => x !== p.key))} />
            <span className="text-sm">{p.label}</span>
          </label>
        ))}
        <div className="flex gap-2">
          <button className="btn-secondary flex-1" onClick={onClose}>Cancel</button>
          <button className="btn-primary flex-1" disabled={busy} onClick={save}>Save permissions</button>
        </div>
      </div>
    </Modal>
  )
}
