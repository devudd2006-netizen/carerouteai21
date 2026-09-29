import { useState } from "react"
import { Navigate, useNavigate } from "react-router-dom"
import { useAuth } from "../auth"
import { post } from "../lib/api"
import { Card, ErrorBox, Field } from "../components/ui"

const RELATIONSHIPS = ["Myself", "Spouse", "Parent", "Son", "Daughter", "Sibling", "Relative", "Friend", "Caregiver", "Other"]
const BLOOD_GROUPS = ["", "A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]
const LANGS = ["English", "தமிழ் (Tamil)", "हिन्दी (Hindi)", "తెలుగు (Telugu)", "ಕನ್ನಡ (Kannada)"]

export default function Onboarding() {
  const { me, refreshMe } = useAuth()
  const nav = useNavigate()
  const [step, setStep] = useState(0)
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)

  const [form, setForm] = useState({
    name: me?.name ?? "", date_of_birth: "", blood_group: "", preferred_language: "English",
    location_text: "", relationship_to_care: "Myself", relationship_other: "",
    accessibility_notes: "", emergency_contact_name: "", emergency_contact_phone: "",
    emergency_contact_relation: "", important_history: "",
  })
  const [allergies, setAllergies] = useState<{ allergen: string; severity: string; reaction: string }[]>([])
  const [conditions, setConditions] = useState<string[]>([])
  const [medications, setMedications] = useState<{ name: string; dosage: string; frequency: string }[]>([])
  const [condInput, setCondInput] = useState("")
  const [al, setAl] = useState({ allergen: "", severity: "MODERATE", reaction: "" })
  const [med, setMed] = useState({ name: "", dosage: "", frequency: "" })

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))
  if (!me || me.role !== "USER") return <Navigate to="/" replace />

  const steps = ["About you", "Care relationship", "Health basics", "Emergency contact", "Review"]
  const next = () => setStep((s) => Math.min(s + 1, steps.length - 1))
  const back = () => setStep((s) => Math.max(s - 1, 0))

  const submit = async () => {
    setErr("")
    setBusy(true)
    try {
      await post("/users/onboard", {
        name: form.name || me.name,
        date_of_birth: form.date_of_birth || null,
        blood_group: form.blood_group || null,
        preferred_language: form.preferred_language,
        location_text: form.location_text || null,
        accessibility_notes: form.accessibility_notes || null,
        relationship_to_care: form.relationship_to_care,
        relationship_other: form.relationship_other || null,
        emergency_contact_name: form.emergency_contact_name || null,
        emergency_contact_phone: form.emergency_contact_phone || null,
        emergency_contact_relation: form.emergency_contact_relation || null,
        important_history: form.important_history || null,
        allergies: allergies.filter((a) => a.allergen.trim()),
        conditions: conditions.filter((c) => c.trim()),
        medications: medications.filter((m) => m.name.trim()),
      })
      await refreshMe()
      nav("/app")
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl p-4 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-black">Welcome to CareRoute AI</h1>
        <p className="muted mt-1">We collect only what’s needed to coordinate your care.</p>
        <div className="mt-4 flex gap-2">
          {steps.map((s, i) => (
            <div key={s} className={`h-1.5 flex-1 rounded-full ${i <= step ? "bg-brand-500" : "bg-slate-200"}`} />
          ))}
        </div>
        <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-brand-700">
          Step {step + 1} of {steps.length} — {steps[step]}
        </p>
      </div>

      <Card>
        {step === 0 && (
          <div className="space-y-4">
            <Field label="Full name">
              <input className="input" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Your name" />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Date of birth">
                <input type="date" className="input" value={form.date_of_birth} onChange={(e) => set("date_of_birth", e.target.value)} />
              </Field>
              <Field label="Blood group (voluntary)">
                <select className="input" value={form.blood_group} onChange={(e) => set("blood_group", e.target.value)}>
                  {BLOOD_GROUPS.map((b) => <option key={b} value={b}>{b || "Prefer not to say"}</option>)}
                </select>
              </Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Preferred language">
                <select className="input" value={form.preferred_language} onChange={(e) => set("preferred_language", e.target.value)}>
                  {LANGS.map((l) => <option key={l}>{l}</option>)}
                </select>
              </Field>
              <Field label="Location (area / city)">
                <input className="input" value={form.location_text} onChange={(e) => set("location_text", e.target.value)} placeholder="e.g. Adyar, Chennai" />
              </Field>
            </div>
            <Field label="Accessibility needs (optional)" hint="Large text, voice support, wheelchair access — anything that helps us serve you better.">
              <input className="input" value={form.accessibility_notes} onChange={(e) => set("accessibility_notes", e.target.value)} />
            </Field>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <Field label="Who are you in relation to the person receiving care?">
              <div className="flex flex-wrap gap-2">
                {RELATIONSHIPS.map((r) => (
                  <button key={r} onClick={() => set("relationship_to_care", r)}
                    className={`rounded-xl border px-4 py-2 text-sm font-semibold transition-colors ${
                      form.relationship_to_care === r ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-300 bg-white"}`}>
                    {r}
                  </button>
                ))}
              </div>
            </Field>
            {form.relationship_to_care === "Other" && (
              <Field label="Describe the relationship">
                <input className="input" value={form.relationship_other} onChange={(e) => set("relationship_other", e.target.value)} />
              </Field>
            )}
            <p className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">
              If you chose a relationship other than <b>Myself</b>: being a family member does
              <b> not</b> automatically grant medical access. The person receiving care explicitly
              controls which information you can see (Caregiver Permissions).
            </p>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-6">
            <div>
              <p className="label">Known conditions</p>
              <div className="mb-2 flex gap-2">
                <input className="input" placeholder="e.g. Type 2 Diabetes" value={condInput}
                  onChange={(e) => setCondInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && condInput.trim()) { setConditions((c) => [...c, condInput.trim()]); setCondInput("") } }} />
                <button className="btn-secondary" onClick={() => { if (condInput.trim()) { setConditions((c) => [...c, condInput.trim()]); setCondInput("") } }}>Add</button>
              </div>
              <div className="flex flex-wrap gap-2">
                {conditions.map((c, i) => (
                  <span key={i} className="pill bg-slate-100">{c} <button className="ml-1 font-bold" onClick={() => setConditions((cs) => cs.filter((_, j) => j !== i))}>✕</button></span>
                ))}
                {conditions.length === 0 && <span className="muted">None added (optional)</span>}
              </div>
            </div>
            <div>
              <p className="label">Allergies</p>
              <div className="mb-2 grid gap-2 sm:grid-cols-3">
                <input className="input" placeholder="Allergen e.g. Penicillin" value={al.allergen} onChange={(e) => setAl({ ...al, allergen: e.target.value })} />
                <select className="input" value={al.severity} onChange={(e) => setAl({ ...al, severity: e.target.value })}>
                  <option>MILD</option><option>MODERATE</option><option>SEVERE</option>
                </select>
                <input className="input" placeholder="Reaction (optional)" value={al.reaction} onChange={(e) => setAl({ ...al, reaction: e.target.value })} />
              </div>
              <button className="btn-secondary" onClick={() => { if (al.allergen.trim()) { setAllergies((a) => [...a, al]); setAl({ allergen: "", severity: "MODERATE", reaction: "" }) } }}>Add allergy</button>
              <div className="mt-2 flex flex-wrap gap-2">
                {allergies.map((a, i) => (
                  <span key={i} className="pill bg-red-100 text-red-700">{a.allergen} · {a.severity}
                    <button className="ml-1 font-bold" onClick={() => setAllergies((as) => as.filter((_, j) => j !== i))}>✕</button></span>
                ))}
              </div>
            </div>
            <div>
              <p className="label">Current medicines</p>
              <div className="mb-2 grid gap-2 sm:grid-cols-3">
                <input className="input" placeholder="Medicine" value={med.name} onChange={(e) => setMed({ ...med, name: e.target.value })} />
                <input className="input" placeholder="Dosage e.g. 500mg" value={med.dosage} onChange={(e) => setMed({ ...med, dosage: e.target.value })} />
                <input className="input" placeholder="Frequency e.g. Twice daily" value={med.frequency} onChange={(e) => setMed({ ...med, frequency: e.target.value })} />
              </div>
              <button className="btn-secondary" onClick={() => { if (med.name.trim()) { setMedications((m) => [...m, med]); setMed({ name: "", dosage: "", frequency: "" }) } }}>Add medicine</button>
              <div className="mt-2 flex flex-wrap gap-2">
                {medications.map((m, i) => (
                  <span key={i} className="pill bg-brand-50 text-brand-700">{m.name} {m.dosage}
                    <button className="ml-1 font-bold" onClick={() => setMedications((ms) => ms.filter((_, j) => j !== i))}>✕</button></span>
                ))}
              </div>
            </div>
            <Field label="Important medical history (optional)">
              <textarea className="input min-h-20" value={form.important_history} onChange={(e) => set("important_history", e.target.value)} placeholder="Surgeries, major events…" />
            </Field>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Emergency contact name">
                <input className="input" value={form.emergency_contact_name} onChange={(e) => set("emergency_contact_name", e.target.value)} />
              </Field>
              <Field label="Emergency contact phone">
                <input className="input" placeholder="+91…" value={form.emergency_contact_phone} onChange={(e) => set("emergency_contact_phone", e.target.value)} />
              </Field>
            </div>
            <Field label="Relationship">
              <input className="input" value={form.emergency_contact_relation} onChange={(e) => set("emergency_contact_relation", e.target.value)} placeholder="e.g. Daughter" />
            </Field>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-3 text-sm">
            <p className="font-semibold">Ready to finish, {form.name || me.name}.</p>
            <ul className="muted list-disc pl-5">
              <li>Conditions: {conditions.length ? conditions.join(", ") : "none added"}</li>
              <li>Allergies: {allergies.length ? allergies.map((a) => a.allergen).join(", ") : "none added"}</li>
              <li>Medicines: {medications.length ? medications.map((m) => m.name).join(", ") : "none added"}</li>
              <li>Emergency contact: {form.emergency_contact_name || "not provided"}</li>
            </ul>
            <p className="rounded-xl bg-brand-50 px-4 py-3 text-brand-800">
              You can edit all of this later in Health Memory. Your data stays private: doctors see
              only speciality-relevant information, and every access is auditable in your Privacy Center.
            </p>
          </div>
        )}

        {err && <div className="mt-4"><ErrorBox message={err} /></div>}

        <div className="mt-6 flex justify-between">
          <button className="btn-secondary" onClick={back} disabled={step === 0 || busy}>Back</button>
          {step < steps.length - 1 ? (
            <button className="btn-primary" onClick={next}>Continue</button>
          ) : (
            <button className="btn-primary" onClick={submit} disabled={busy}>{busy ? "Saving…" : "Complete onboarding"}</button>
          )}
        </div>
      </Card>
    </div>
  )
}
