import { useState } from "react"
import { Link, Navigate } from "react-router-dom"
import { useAuth } from "../auth"
import { Card, ErrorBox, Field, SuccessBox } from "../components/ui"


export default function Login() {
  const { me, requestOtp, loginWithOtp } = useAuth()
  const [identifier, setIdentifier] = useState("")
  const [code, setCode] = useState("")
  const [stage, setStage] = useState<"id" | "otp">("id")
  const [demoOtp, setDemoOtp] = useState<string | null>(null)
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)

  if (me) return <Navigate to="/" replace />

  const send = async (id?: string) => {
    setErr("")
    setBusy(true)
    try {
      const ident = (id ?? identifier).trim()
      setIdentifier(ident)
      const res = await requestOtp(ident)
      setDemoOtp(res.demo_otp)
      setStage("otp")
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  const verify = async () => {
    setErr("")
    setBusy(true)
    try {
      await loginWithOtp(identifier, code.trim())
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }



  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-b from-brand-50 to-slate-50 p-4">
      <div className="w-full max-w-4xl">
        <div className="mb-8 text-center">
          <span className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600 text-2xl font-black text-white">C</span>
          <h1 className="text-3xl font-black tracking-tight">CareRoute AI</h1>
          <p className="mt-1 font-semibold text-brand-700">One Care Journey. Every Right Connection.</p>
          <p className="muted mx-auto mt-2 max-w-xl">
            A multi-hospital healthcare coordination prototype. Identity + role + relationship +
            purpose + permission decide what information is visible — never just “logged in”.
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <h2 className="section-title mb-4">Sign in securely</h2>
            {stage === "id" ? (
              <div className="space-y-4">
                <Field label="Phone number or Staff / Doctor / Admin / Worker ID" hint="New here? Just enter your phone — we’ll create your account after verification.">
                  <input className="input" placeholder="+91 98400 00001 or DOC101"
                    value={identifier} onChange={(e) => setIdentifier(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && identifier && send()} />
                </Field>
                <button className="btn-primary w-full" disabled={!identifier || busy} onClick={() => send()}>
                  {busy ? "Sending…" : "Send verification code (MFA)"}
                </button>
                <p className="text-xs text-ink-500">
                  Prototype: the MFA code is shown on screen instead of being sent by SMS.
                  A production deployment sends it through an SMS gateway.
                </p>
                {err && <ErrorBox message={err} />}
              </div>
            ) : (
              <div className="space-y-4">
                {demoOtp && (
                  <SuccessBox message={`Prototype MFA code: ${demoOtp} (never sent over a real channel)`} />
                )}
                <Field label={`Enter the 6-digit code for ${identifier}`}>
                  <input className="input text-center text-2xl font-black tracking-[0.4em]"
                    inputMode="numeric" maxLength={6} value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                    onKeyDown={(e) => e.key === "Enter" && code.length === 6 && verify()} />
                </Field>
                <button className="btn-primary w-full" disabled={code.length !== 6 || busy} onClick={verify}>
                  Verify & sign in
                </button>
                <button className="btn-ghost w-full" onClick={() => setStage("id")}>Use a different number</button>
                {err && <ErrorBox message={err} />}
              </div>
            )}
            <p className="mt-4 text-center text-xs text-ink-500">
              Device passkey-style unlock can be enrolled after signing in (Profile → Security).
              No biometric images are ever stored.
            </p>
          </Card>

          <Card>
            <h2 className="section-title mb-1">Role-based access</h2>
            <p className="muted mb-4">CareRoute uses the same secure sign-in flow for every role. The account's
              server-side role determines which dashboard and patient information can be accessed.</p>
            <div className="space-y-2">
              {[
                ["User / Patient", "Personal health journey and care navigation"],
                ["Caregiver", "Only permissions explicitly granted by the user"],
                ["Community Health Worker", "Assigned users and wellness follow-up"],
                ["Hospital Staff", "Appointments and operational workflow"],
                ["Doctor", "Speciality-scoped clinical access"],
                ["Hospital Admin", "Hospital administration and audit controls"],
              ].map(([role, desc]) => (
                <div key={role} className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                  <p className="text-sm font-bold">{role}</p>
                  <p className="text-xs text-ink-500">{desc}</p>
                </div>
              ))}
            </div>
            <p className="mt-4 text-xs text-ink-500">
              For the multi-laptop presentation, sign each laptop into its assigned account using its normal
              phone number or authorized staff/doctor/admin/worker ID.
            </p>
          </Card>
        </div>
        <p className="mt-6 text-center text-xs text-ink-500">
          <Link to="/login" className="underline">Privacy & permissions</Link> · Hospital information is
          publicly verified; clinical data is synthetic. Not a medical device.
        </p>
      </div>
    </div>
  )
}
