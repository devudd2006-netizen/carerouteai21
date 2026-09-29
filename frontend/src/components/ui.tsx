import type { HTMLAttributes, ReactNode } from "react"

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`card p-5 ${className}`}>{children}</div>
}

export function Pill({ tone = "slate", children }: { tone?: "green" | "amber" | "red" | "slate" | "blue"; children: ReactNode }) {
  const tones: Record<string, string> = {
    green: "bg-emerald-100 text-emerald-800",
    amber: "bg-amber-100 text-amber-800",
    red: "bg-red-100 text-red-700",
    slate: "bg-slate-100 text-slate-700",
    blue: "bg-sky-100 text-sky-800",
  }
  return <span className={`pill ${tones[tone]}`}>{children}</span>
}

export function StatusPill({ status }: { status: string }) {
  const map: Record<string, "green" | "amber" | "red" | "slate" | "blue"> = {
    CONFIRMED: "green", COMPLETED: "blue", REQUESTED: "amber",
    RESCHEDULED: "amber", RESCHEDULED_MOVED: "slate", REJECTED: "red", ACTIVE: "green",
    RESOLVED: "slate", PENDING: "amber",
  }
  return <Pill tone={map[status] ?? "slate"}>{status.replace("_", " ")}</Pill>
}

export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="card p-10 text-center">
      <div className="text-4xl mb-2">🗂️</div>
      <p className="font-semibold text-ink-900">{title}</p>
      {hint && <p className="muted mt-1">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Unavailable({ label = "Live availability unavailable", why }: { label?: string; why?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-3 text-sm text-ink-500">
      <span className="font-semibold text-ink-700">{label}</span>
      {why ? <span> — {why}</span> : null}
    </div>
  )
}

export function ErrorBox({ message }: { message: string }) {
  if (!message) return null
  return <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{message}</div>
}

export function SuccessBox({ message }: { message: string }) {
  if (!message) return null
  return <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{message}</div>
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-ink-500">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
      <span className="text-sm">{label}</span>
    </div>
  )
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div>
      <label className="label">{label}</label>
      {children}
      {hint && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
    </div>
  )
}

export function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="card w-full max-w-lg max-h-[90vh] overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold">{title}</h3>
          <button className="btn-secondary !px-2.5 !py-1" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {subtitle && <p className="muted mt-1 max-w-2xl">{subtitle}</p>}
      </div>
      {right}
    </div>
  )
}

export function Stat({ label, value, tone = "slate", ...rest }:
  { label: string; value: string | number; tone?: "green" | "amber" | "red" | "slate" | "blue" } & HTMLAttributes<HTMLDivElement>) {
  const bar: Record<string, string> = {
    green: "bg-emerald-500", amber: "bg-amber-500", red: "bg-red-500",
    slate: "bg-slate-400", blue: "bg-sky-500",
  }
  return (
    <div className="card p-4" {...rest}>
      <div className={`mb-2 h-1 w-8 rounded-full ${bar[tone]}`} />
      <p className="text-2xl font-bold">{value}</p>
      <p className="muted">{label}</p>
    </div>
  )
}
