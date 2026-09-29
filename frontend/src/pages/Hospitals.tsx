import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { get } from "../lib/api"
import { useSearchLocation } from "../lib/location"
import { AppointmentDiscovery } from "./Appointments"
import DiscoveryDebug from "../components/DiscoveryDebug"
import { Card, ErrorBox, PageHeader, Pill, Spinner } from "../components/ui"
import type { Hospital } from "../lib/types"
import SimpleMap, { navUrl } from "../components/SimpleMap"

interface DiscoverResponse {
  facilities: (Hospital & { why?: string[] })[]
  in_radius: (Hospital & { why?: string[] })[]
  nearest_outside_km: number | null
  next_radius_km: number | null
  data_source: string
  provider_failed?: boolean
  needs_location?: boolean
  provider: { provider: string; mode: string }
  search: { lat: number | null; lng: number | null; location_text: string | null; query: string | null; speciality: string | null; emergency: boolean; multi_specialty: boolean; highly_rated: boolean; radius_km: number }
  ranking_factors: string[]
  disclaimer: string
  fallback_note?: string
}

const QUICK_NEEDS: { label: string; query?: string; speciality?: string; emergency?: boolean }[] = [
  { label: "🦴 Orthopedics", speciality: "orthopaedics" },
  { label: "❤️ Cardiology", speciality: "cardiology" },
  { label: "👁️ Eye care", speciality: "ophthalmology" },
  { label: "🩺 General medicine", speciality: "general_medicine" },
  { label: "🚨 Emergency care", emergency: true },
  { label: "🏥 Any hospital", query: "hospital" },
]

const RADII = [2, 5, 10, 25, 100]

export default function Hospitals() {
  const { loc, status, accuracyNote, useMyLocation, searchManual } = useSearchLocation()
  const [manualText, setManualText] = useState("")

  // Automatically request location once on first entry; the shared session cache
  // prevents repeated permission prompts across CareRoute pages.
  useEffect(() => {
    if (!loc && status === "idle") useMyLocation().catch(() => undefined)
  }, [loc, status, useMyLocation])
  const [result, setResult] = useState<DiscoverResponse | null>(null)
  const [query, setQuery] = useState("")
  const [need, setNeed] = useState<{ query?: string; speciality?: string; emergency?: boolean }>({})
  const [multiSpecialty, setMultiSpecialty] = useState(false)
  const [highlyRated, setHighlyRated] = useState(false)
  const [radius, setRadius] = useState(5)
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)
  const [requestFor, setRequestFor] = useState<number | null>(null)
  const [apiFailed, setApiFailed] = useState(false)
  const [apiStatus, setApiStatus] = useState<string | null>(null)

  const load = useCallback(async (opts?: {
    lat?: number | null; lng?: number | null; q?: string; need?: typeof need;
    multi?: boolean; rated?: boolean; r?: number
  }) => {
    setBusy(true); setErr("")
    try {
      const p = new URLSearchParams()
      const lat = opts?.lat !== undefined ? opts.lat : loc?.lat
      const lng = opts?.lng !== undefined ? opts.lng : loc?.lng
      if (lat != null && lng != null) { p.set("lat", String(lat)); p.set("lng", String(lng)) }
      const q = opts?.q ?? query
      if (q.trim()) p.set("query", q.trim())
      const n = opts?.need ?? need
      if (n.speciality) p.set("speciality", n.speciality)
      if (n.emergency) p.set("emergency", "true")
      const multi = opts?.multi ?? multiSpecialty
      const rated = opts?.rated ?? highlyRated
      if (multi) p.set("multi_specialty", "true")
      if (rated) p.set("highly_rated", "true")
      p.set("radius_km", String(opts?.r ?? radius))
      const r = await get<DiscoverResponse>(`/hospitals/discover?${p}`)
      setResult(r)
      setApiFailed(!!r.provider_failed)
      setApiStatus(r.provider_failed ? "FAILED" : `OK · ${r.data_source}`)
    } catch (e: any) { setErr(e.message); setApiFailed(true); setApiStatus("NETWORK ERROR") } finally { setBusy(false) }
  }, [loc, query, need, multiSpecialty, highlyRated, radius])

  // §20: initial load + reload ONLY when location/radius/filters change.
  useEffect(() => { load() }, [load])

  // §15 handoff: Find Care can link here with a pre-identified speciality.
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search).get("speciality")
    if (sp) setNeed({ speciality: sp })
  }, [])

  const submitManual = async () => {
    if (!manualText.trim()) return
    const ok = await searchManual(manualText)
    if (!ok) setErr(`Could not find "${manualText.trim()}". Try a city or area name like "Vellore" or "Near Tirunelveli".`)
    setManualText("")
  }

  const pickNeed = (n: typeof need) => {
    setNeed(n)
    load({ need: n })
  }

  const facilities = result?.facilities ?? []
  const inRadius = result?.in_radius ?? facilities
  const live = result?.data_source === "GOOGLE_PLACES_LIVE"

  return (
    <div className="space-y-6">
      <PageHeader title="Find Hospitals"
        subtitle="How can we help you today? Search by need, speciality or hospital — results follow your location." />

      {/* Search bar */}
      <Card>
        <div className="flex flex-wrap gap-2">
          <input className="input flex-1 min-w-56" placeholder="Search a hospital, speciality or healthcare need — e.g. 'eye emergency', 'Government hospital'"
            value={query} onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()} />
          <button className="btn-primary" disabled={busy} onClick={() => load()}>
            {busy ? "Searching…" : "Search"}
          </button>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {QUICK_NEEDS.map((n) => (
            <button key={n.label}
              className={`rounded-xl border px-3 py-1.5 text-sm font-semibold transition-colors ${
                (need.speciality && need.speciality === n.speciality) || (need.emergency && n.emergency)
                  ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200 text-ink-700 hover:bg-slate-50"}`}
              onClick={() => pickNeed((need.speciality === n.speciality && need.emergency === n.emergency) ? {} : n)}>
              {n.label}
            </button>
          ))}
        </div>

        {/* §3 result filters */}
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
          <span className="label !mb-0">Filters:</span>
          <button onClick={() => { setMultiSpecialty((v) => !v) }}
            className={`rounded-xl border px-3 py-1.5 text-sm font-semibold ${multiSpecialty ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200"}`}>
            Multi-specialty
          </button>
          <button onClick={() => { setHighlyRated((v) => !v) }}
            className={`rounded-xl border px-3 py-1.5 text-sm font-semibold ${highlyRated ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200"}`}
            title="Shows only facilities with genuine public rating data">
            Highly rated
          </button>
          <span className="label !mb-0 ml-2">Within:</span>
          {RADII.map((r) => (
            <button key={r} onClick={() => setRadius(r)}
              className={`rounded-xl border px-3 py-1.5 text-sm font-semibold ${
                radius === r ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200"}`}>
              {r} km
            </button>
          ))}
        </div>
      </Card>

      {/* §3 location component */}
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <p className="label !mb-0">📍 Your location</p>
          {loc ? (
            <Pill tone="blue">{status === "granted" ? "Using your current location" : "Search location"} — {loc.label}</Pill>
          ) : (
            <span className="text-sm text-ink-500">not set — results are not distance-ranked</span>
          )}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button className="btn-secondary !py-2" disabled={status === "locating"} onClick={useMyLocation}>
            {status === "locating" ? "Locating…" : loc?.source === "device" ? "Refresh my location" : "Use my current location"}
          </button>
          <span className="text-sm text-ink-500">or</span>
          <input className="input !w-64" placeholder="Search another location — e.g. Vellore, Near Tirunelveli"
            value={manualText} onChange={(e) => setManualText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submitManual()} />
          <button className="btn-secondary !py-2" onClick={submitManual}>Search another location</button>
        </div>
        {status === "denied" && (
          <p className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
            Location access was not granted. Nothing is assumed — set a search location above, or results run without distance ranking.
          </p>
        )}
        {accuracyNote && (
          <p className={`mt-2 rounded-xl px-3 py-2 text-xs ${accuracyNote.includes("approximate") ? "bg-amber-50 text-amber-800" : "bg-slate-50 text-ink-600"}`}>
            📍 {accuracyNote}
            {accuracyNote.includes("approximate") && (
              <button className="ml-2 font-semibold underline" onClick={useMyLocation}>Retry Location</button>
            )}
          </p>
        )}
      </Card>

      <DiscoveryDebug loc={loc} radius={radius} provider={result?.provider}
        status={apiStatus} count={result?.facilities?.length} failed={apiFailed} />

      {err && <ErrorBox message={err} />}

      {/* §7: honest provider-failure state — never fake hospitals */}
      {apiFailed && (
        <Card className="p-8 text-center">
          <p className="font-semibold">Nearby healthcare information is temporarily unavailable.</p>
          <p className="muted mt-1">The live healthcare place search could not be reached. No substitute data is shown.</p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            <button className="btn-primary" onClick={() => load()}>Try Again</button>
            <button className="btn-secondary" onClick={() => document.querySelector('input[placeholder^="Search another location"]')?.scrollIntoView({ block: "center" })}>Change Location</button>
          </div>
        </Card>
      )}

      {/* §7: no-coordinates state for live search */}
      {result?.needs_location && (
        <Card className="p-8 text-center">
          <p className="font-semibold">Set your location to search nearby healthcare.</p>
          <p className="muted mt-1">Real nearby search needs coordinates — use your device location or search for an area above.</p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            <button className="btn-primary" onClick={useMyLocation}>Use my current location</button>
          </div>
        </Card>
      )}

      {result && !result.needs_location && !apiFailed && (
        <>
          {/* Honest data-source banner */}
          <div className={`rounded-xl border px-4 py-3 text-sm ${live ? "border-emerald-200 bg-emerald-50 text-emerald-800" : result.data_source === "OPENSTREETMAP_OVERPASS" ? "border-sky-200 bg-sky-50 text-sky-800" : "border-slate-200 bg-slate-50 text-ink-600"}`}>
            {live
              ? <>🌐 <b>Live discovery</b> — results from Google Places for this location. Public place information only; live bed/slot availability is not available.</>
              : result.data_source === "OPENSTREETMAP_OVERPASS"
                ? <>🗺️ <b>Live nearby search</b> — real mapped healthcare facilities from OpenStreetMap around your coordinates. Public place information only.</>
                : <>🗂️ <b>Prototype directory</b> — verified demonstration hospitals (demo provider mode).</>}
          </div>

          <SimpleMap points={facilities.filter((h) => h.latitude != null && h.longitude != null)
            .map((h) => ({ id: h.place_id ?? h.id, lat: h.latitude, lng: h.longitude, label: h.name, sub: h.address }))}
            center={loc ? [loc.lat, loc.lng] : null} />

          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="muted">{inRadius.length} facilit{inRadius.length === 1 ? "y" : "ies"} within {radius} km
              {loc ? ` of ${loc.label}` : ""}{need.speciality ? ` · ${need.speciality.replace("_", " ")}` : ""}
            </p>
            <p className="text-xs text-ink-500">CareRoute discovery factors: {result.ranking_factors.join(" · ")}</p>
          </div>

          {facilities.length === 0 && (
            <Card className="p-8 text-center">
              <p className="font-semibold">No hospitals match this search.</p>
              <p className="muted mt-1">Try a different location, clear filters, or search a broader need like "hospital".</p>
            </Card>
          )}

          {/* §17 radius empty state with expansion */}
          {facilities.length === 0 && !apiFailed && (
            <Card className="p-8 text-center">
              <p className="font-semibold">No hospitals found within {radius} km.</p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {result.next_radius_km && (
                  <button className="btn-primary" onClick={() => setRadius(result.next_radius_km!)}>
                    Expand Search Radius ({result.next_radius_km} km)
                  </button>
                )}
                <button className="btn-secondary" onClick={() => document.querySelector('input[placeholder^="Search another location"]')?.scrollIntoView({ block: "center" })}>Change Location</button>
              </div>
            </Card>
          )}
          {facilities.length > 0 && inRadius.length === 0 && (
            <Card className="p-8 text-center">
              <p className="font-semibold">
                No suitable hospital found within {radius} km{need.speciality ? " for this speciality" : ""}.
              </p>
              {result.nearest_outside_km != null && (
                <p className="muted mt-1">Nearest matching facility is ≈ {result.nearest_outside_km} km away.</p>
              )}
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {result.next_radius_km && (
                  <button className="btn-primary" onClick={() => setRadius(result.next_radius_km!)}>
                    Search within {result.next_radius_km} km
                  </button>
                )}
                <a className="btn-secondary" href="#top">Change location</a>
                <button className="btn-secondary" onClick={() => { setNeed({}); setQuery(""); setMultiSpecialty(false); setHighlyRated(false) }}>
                  View all nearby hospitals
                </button>
            </div>
            </Card>
          )}

          <div className="space-y-3">
            {(inRadius.length > 0 ? inRadius : facilities).map((h) => (
              <Card key={h.place_id ?? h.id} className="flex flex-wrap items-center justify-between gap-4">
                <div className="min-w-64 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-bold">{h.name}</p>
                    <Pill tone={h.hospital_type === "Government" ? "blue" : h.hospital_type === "Private" ? "slate" : "green"}>{h.hospital_type}</Pill>
                    {h.distance_km != null && <Pill tone="slate">≈ {h.distance_km} km</Pill>}
                    {h.public_rating != null && (
                      <Pill tone="amber">★ {h.public_rating}{h.public_rating_count ? ` (${h.public_rating_count})` : ""}</Pill>
                    )}
                    {h.open_now != null && <Pill tone={h.open_now ? "green" : "red"}>{h.open_now ? "Open now" : "Closed"}</Pill>}
                  </div>
                  <p className="muted mt-0.5">{h.address || "Information unavailable"}{h.city ? ` · ${h.city}` : ""}</p>
                  {h.why && h.why.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {h.why.map((w) => <span key={w} className="pill bg-brand-50 text-brand-700">{w}</span>)}
                    </div>
                  )}
                  {h.departments.length > 0 ? (
                    <p className="mt-1 text-xs text-ink-500">
                      Specialities: {h.departments.map((d) => d.speciality_key.replace("_", " ")).slice(0, 5).join(", ")}
                      {h.departments.length > 5 ? "…" : ""}
                    </p>
                  ) : (
                    <p className="mt-1 text-xs text-ink-500">Speciality information unavailable for live-listed facilities</p>
                  )}
                  <div className="mt-1 flex flex-wrap gap-1">
                    {Object.entries(h.verified_fields ?? {}).filter(([, v]) => v).slice(0, 3)
                      .map(([k]) => <span key={k} className="pill bg-emerald-50 text-emerald-700">✓ {k.replace("_", " ")} verified</span>)}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {/* §19: the full journey visible on every card */}
                  {!h.place_id && (
                    <button className="btn-primary" onClick={() => setRequestFor(h.id)}>Request Appointment</button>
                  )}
                  {h.latitude != null && h.longitude != null && (
                    <a className="btn-secondary" href={navUrl(h.latitude, h.longitude, h.name, loc ? { lat: loc.lat, lng: loc.lng } : null)} target="_blank" rel="noreferrer">
                      🧭 Get Directions
                    </a>
                  )}
                  {h.phone && <a className="btn-secondary" href={`tel:${h.phone}`}>📞 Call</a>}
                  {h.place_id ? (
                    h.website && <a className="btn-secondary" href={h.website} target="_blank" rel="noreferrer">Website</a>
                  ) : (
                    <Link className="btn-secondary" to={`/app/hospitals/${h.id}`}>View Hospital</Link>
                  )}
                </div>
              </Card>
            ))}
          </div>

          <p className="text-xs text-ink-500">{result.disclaimer}</p>
        </>
      )}
      {busy && !result && <Spinner />}

      {requestFor != null && (
        <AppointmentDiscovery initialHospitalId={requestFor}
          onClose={() => setRequestFor(null)}
          onBooked={() => { setRequestFor(null); window.location.href = "/app/appointments" }} />
      )}
    </div>
  )
}
