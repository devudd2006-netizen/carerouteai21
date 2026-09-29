// CareRoute AI — cross-dashboard live synchronization.
//
// Polls the cheap /sync token endpoint; when the token changes it dispatches a
// `cr_sync` window event and runs the shell-level callback (badge + toast).
// This is what makes the four-laptop demonstration genuinely live: receptionist
// confirms on laptop 2 → the user's dashboard on laptop 1 updates within ~3s.
import { useEffect, useRef, useState } from "react"
import { get } from "./api"

export const SYNC_EVENT = "cr_sync"

export function useSync(onSync?: () => unknown | Promise<unknown>, enabled = true) {
  const cbRef = useRef(onSync)
  cbRef.current = onSync
  const tokenRef = useRef<string | null>(null)

  useEffect(() => {
    if (!enabled) return
    let stop = false
    let timer: number | undefined
    const poll = async () => {
      try {
        const r = await get<{ sync_token: string; poll_after_seconds: number }>("/sync")
        if (stop) return
        if (tokenRef.current !== null && r.sync_token !== tokenRef.current) {
          window.dispatchEvent(new Event(SYNC_EVENT))
          try { await cbRef.current?.() } catch { /* callback handles its own errors */ }
        }
        tokenRef.current = r.sync_token
        timer = window.setTimeout(poll, (r.poll_after_seconds || 3) * 1000)
      } catch {
        if (!stop) timer = window.setTimeout(poll, 8000) // backend hiccup: slow retry
      }
    }
    poll()
    return () => { stop = true; if (timer) window.clearTimeout(timer) }
  }, [enabled])
}

/** Live data hook: loads now and re-loads whenever a sync event arrives. */
export function useLiveReload(load: () => unknown | Promise<unknown>, enabled = true) {
  const loadRef = useRef(load)
  loadRef.current = load
  useEffect(() => {
    if (!enabled) return
    const handler = () => { try { loadRef.current() } catch { /* page handles errors */ } }
    window.addEventListener(SYNC_EVENT, handler)
    return () => window.removeEventListener(SYNC_EVENT, handler)
  }, [enabled])
}

// ------------------------------------------------------ unread badge + toast
export function useUnread() {
  const [unread, setUnread] = useState(0)
  const refresh = async (): Promise<string | null> => {
    try {
      const r = await get<{ unread: number; notifications: { title: string; read: boolean }[] }>
        ("/notifications")
      setUnread(r.unread || 0)
      const first = r.notifications?.find((n) => !n.read)
      return first ? first.title : null
    } catch { return null }
  }
  useEffect(() => { refresh() }, [])
  return { unread, refresh }
}

export function Toast({ message, onDone }: { message: string | null; onDone: () => void }) {
  if (!message) return null
  return (
    <div className="fixed bottom-6 right-6 z-50 max-w-sm rounded-xl border border-brand-200 bg-white px-4 py-3 shadow-xl">
      <p className="text-sm font-bold text-brand-700">🔔 Live update</p>
      <p className="muted mt-0.5">{message}</p>
      <button className="mt-2 text-xs font-semibold text-ink-500 underline" onClick={onDone}>Dismiss</button>
    </div>
  )
}
