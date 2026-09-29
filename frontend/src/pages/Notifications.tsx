import { useCallback, useEffect, useState } from "react"
import { get, post } from "../lib/api"
import { useLiveReload } from "../lib/sync"
import { Card, Empty, PageHeader, Pill, Spinner } from "../components/ui"
import type { Notification } from "../lib/types"

export default function Notifications() {
  const [items, setItems] = useState<Notification[] | null>(null)
  const load = useCallback(async () => {
    try {
      const r = await get<{ notifications: Notification[] }>("/notifications")
      setItems(r.notifications)
    } catch { /* signed out */ }
  }, [])
  useEffect(() => { load() }, [load])
  useLiveReload(load)  // live: new notifications appear while the page is open

  if (!items) return <Spinner />
  const unread = items.filter((n) => !n.read).length

  return (
    <div className="space-y-6">
      <PageHeader title="Notifications"
        subtitle="Appointment updates, prescriptions, wellness follow-ups and emergency status — no unnecessary medical alarms."
        right={unread > 0 ? (
          <button className="btn-secondary" onClick={async () => { await post("/notifications/read-all"); await load() }}>
            Mark all read ({unread})
          </button>
        ) : undefined} />
      {items.length === 0 ? <Empty title="Nothing yet" hint="Notifications about your appointments and prescriptions will appear here." /> : (
        <div className="space-y-2">
          {items.map((n) => (
            <Card key={n.id} className={`!py-3 ${n.read ? "" : "!border-brand-200 !bg-brand-50/40"}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-bold">{n.title}</p>
                  <p className="muted">{n.body}</p>
                </div>
                <div className="text-right">
                  <Pill tone={n.type.includes("EMERGENCY") ? "red" : n.type.includes("CONFIRMED") ? "green" : "slate"}>
                    {n.type.replace(/_/g, " ").toLowerCase()}
                  </Pill>
                  <p className="mt-1 text-[11px] text-ink-500">{String(n.created_at).slice(0, 16).replace("T", " ")}</p>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
