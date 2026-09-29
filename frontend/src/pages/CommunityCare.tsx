import { useEffect, useState } from "react"
import { get } from "../lib/api"
import { Card, PageHeader, Pill, Spinner, Unavailable } from "../components/ui"

export default function CommunityCare() {
  const [me, setMe] = useState<any | null>(null)
  useEffect(() => { get<any>("/auth/me").then(setMe) }, [])
  if (!me) return <Spinner />

  return (
    <div className="space-y-6">
      <PageHeader title="Community Care"
        subtitle="Authorized community health workers support elderly and digitally underserved users — with strict, auditable limits." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h3 className="section-title mb-3">How community support works</h3>
          <ol className="ml-4 list-decimal space-y-2 text-sm">
            <li>A verified community health worker is assigned to support you (with your consent).</li>
            <li>They can help with <b>wellness visits</b>, appointment requests and navigation.</li>
            <li>If you haven't been active for 10–15 days, they see <b>“wellness follow-up required”</b> — never an automatic emergency alarm. They check on you and decide the real situation.</li>
            <li>They see only: your appointments, basic profile and medication list. Never your full history or reports.</li>
            <li>Every visit and every access is recorded in your Privacy Center.</li>
          </ol>
        </Card>
        <div className="space-y-4">
          <Card>
            <h3 className="section-title mb-2">Your assigned community worker</h3>
            <p className="muted">
              In this prototype, CHW <b>Selvi Amirtham</b> (ID CHW042, Chennai City Community Health
              Programme — demo) is assigned to demo patient Kamala Devi. Your own account has no
              assigned worker — assignment happens through a community health programme.
            </p>
            <div className="mt-3"><Pill tone="blue">Programme affiliation is verified at onboarding of the worker</Pill></div>
          </Card>
          <Card>
            <h3 className="section-title mb-2">Wellness check reminders</h3>
            <p className="muted">Gentle follow-ups only — CareRoute never raises medical alarms from inactivity.</p>
            <div className="mt-2"><Unavailable label="Automated call reminders unavailable" why="no telephony integration in the prototype; workers follow up in person." /></div>
          </Card>
        </div>
      </div>
    </div>
  )
}
