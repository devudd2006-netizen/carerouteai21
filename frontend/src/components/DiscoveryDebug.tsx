import type { SearchLocation } from "../lib/location"

/** Development-only discovery debug panel (§19). Hidden in production builds. */
export default function DiscoveryDebug({ loc, radius, provider, status, count, failed }:
  { loc: SearchLocation | null; radius: number; provider?: { provider: string; mode: string } | null;
    status?: string | null; count?: number | null; failed?: boolean }) {
  if (import.meta.env.PROD) return null
  return (
    <details className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-2 text-xs text-ink-500">
      <summary className="cursor-pointer font-semibold">🔧 Discovery debug (dev builds only)</summary>
      <div className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
        <p>GPS latitude: <b>{loc?.lat?.toFixed(6) ?? "—"}</b></p>
        <p>GPS longitude: <b>{loc?.lng?.toFixed(6) ?? "—"}</b></p>
        <p>GPS accuracy: <b>{loc?.accuracy_m != null ? `${loc.accuracy_m} m` : "—"}</b></p>
        <p>Selected search location: <b>{loc ? `${loc.label} (${loc.source})` : "none"}</b></p>
        <p>Search radius: <b>{radius} km</b></p>
        <p>Healthcare API: <b>{provider?.provider ?? "—"}</b> · {provider?.mode ?? "—"}</p>
        <p>API response status: <b>{failed ? "FAILED" : status ?? "—"}</b></p>
        <p>Returned hospitals: <b>{count ?? "—"}</b></p>
      </div>
    </details>
  )
}
