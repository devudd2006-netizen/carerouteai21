import { useCallback, useEffect, useState } from "react"
import { get } from "../lib/api"
import { useSearchLocation } from "../lib/location"
import { Card, ErrorBox, PageHeader, Pill, Spinner } from "../components/ui"
import SimpleMap, { navUrl } from "../components/SimpleMap"

interface Camp {
  id: number; name: string; camp_date: string; location_text: string
  latitude: number | null; longitude: number | null; speciality: string
  services: string; organizer: string; registration: string; contact: string
  verified_source: string; distance_km: number | null; _demo?: boolean
}

const RADII = [2, 5, 10, 25, 100]

export default function MedicalCamps() {
  const { loc, status, useMyLocation, searchManual } = useSearchLocation()
  const [manualText, setManualText] = useState("")
  const [camps, setCamps] = useState<Camp[] | null>(null)
  const [note, setNote] = useState("")
  const [radius, setRadius] = useState(10)
  const [err, setErr] = useState("")

  // Automatically request location once on first entry; the shared session cache
  // prevents repeated permission prompts across CareRoute pages.
  useEffect(() => {
    if (!loc && status === "idle") useMyLocation().catch(() => undefined)
  }, [loc, status, useMyLocation])

  const load = useCallback(async (r?: number) => {
    setErr("")
    try {
      const p = new URLSearchParams()
      if (loc) { p.set("lat", String(loc.lat)); p.set("lng", String(loc.lng)); p.set("location_text", loc.label) }
      p.set("radius_km", String(r ?? radius))
      const res = await get<{ camps: Camp[]; empty_note: string }>(`/medical-camps?${p}`)
      setCamps(res.camps)
      setNote(res.empty_note)
    } catch (e: any) { setErr(e.message); setCamps([]) }
  }, [loc, radius])

  // §20: reload only when location or radius changes.
  useEffect(() => { load() }, [load])

  const submitManual = async () => {
    if (!manualText.trim()) return
    const ok = await searchManual(manualText)
    if (!ok) setErr(`Could not find "${manualText.trim()}". Try a city or area name.`)
    setManualText("")
  }

  const today = new Date().toISOString().slice(0, 10)

  return (
    <div className="space-y-6">
      <PageHeader title="Medical Camps"
        subtitle="Free community camps near you. Only verified listings are shown — demo entries are clearly labeled, and none are invented." />

      {/* §3 location component + radius (§13) */}
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <p className="label !mb-0">📍 Your location</p>
          {loc ? (
            <Pill tone="blue">{status === "granted" ? "Using your current location" : "Search location"} — {loc.label}</Pill>
          ) : (
            <span className="text-sm text-ink-500">not set — enable location to see nearby camps</span>
          )}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button className="btn-secondary !py-2" disabled={status === "locating"} onClick={useMyLocation}>
            {status === "locating" ? "Locating…" : loc?.source === "device" ? "Refresh my location" : "Use my current location"}
          </button>
          <span className="text-sm text-ink-500">or</span>
          <input className="input !w-64" placeholder="Search another location — e.g. Vellore"
            value={manualText} onChange={(e) => setManualText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submitManual()} />
          <button className="btn-secondary !py-2" onClick={submitManual}>Search another location</button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="label !mb-0">Within:</span>
          {RADII.map((r) => (
            <button key={r} onClick={() => setRadius(r)}
              className={`rounded-xl border px-3 py-1.5 text-sm font-semibold ${
                radius === r ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200"}`}>
              {r} km
            </button>
          ))}
        </div>
        {status === "denied" && (
          <p className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
            Location access was not granted. Set a search location above — nothing is assumed.
          </p>
        )}
      </Card>

      {err && <ErrorBox message={err} />}

      {camps === null ? <Spinner /> : camps.length === 0 ? (
        <Card className="p-10 text-center">
          <div className="text-4xl">⛺</div>
          <p className="mt-2 font-semibold">No verified medical camps found within {radius} km{loc ? ` of ${loc.label}` : ""}.</p>
          <p className="muted mx-auto mt-1 max-w-md">{note}</p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            <button className="btn-primary" onClick={() => setRadius(radius === 2 ? 5 : radius === 5 ? 10 : radius === 10 ? 25 : 100)}>
              Search within {radius === 2 ? 5 : radius === 5 ? 10 : radius === 10 ? 25 : 100} km
            </button>
            <button className="btn-secondary" onClick={useMyLocation}>Change location</button>
          </div>
        </Card>
      ) : (
        <>
          <SimpleMap points={camps.filter((c) => c.latitude != null && c.longitude != null).map((c) => ({
            id: c.id, lat: c.latitude!, lng: c.longitude!, label: c.name,
            sub: `${c.camp_date} · ${c.location_text}`,
          }))} height={280} center={loc ? [loc.lat, loc.lng] : null} />
          <div className="grid gap-4 lg:grid-cols-2">
            {camps.map((c) => (
              <Card key={c.id}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-bold">{c.name}</p>
                    <p className="muted">{c.location_text}</p>
                  </div>
                  <div className="text-right">
                    <Pill tone={c.camp_date >= today ? "green" : "slate"}>
                      {c.camp_date >= today ? c.camp_date : "completed"}
                    </Pill>
                    {c.distance_km != null && <p className="mt-1 text-xs font-semibold text-ink-500">≈ {c.distance_km} km</p>}
                  </div>
                </div>
                <p className="mt-2 text-sm"><b>Speciality:</b> {c.speciality}</p>
                <p className="text-sm"><b>Services:</b> {c.services}</p>
                <p className="text-sm"><b>Organizer:</b> {c.organizer}</p>
                <p className="text-sm"><b>Registration:</b> {c.registration} · ☎ {c.contact}</p>
                <div className="mt-3 flex items-center justify-between">
                  <span className={`pill ${c._demo ? "bg-amber-50 text-amber-700" : "bg-emerald-50 text-emerald-700"}`}>
                    {c._demo ? "demo listing (prototype)" : `verified · ${c.verified_source}`}
                  </span>
                  {c.latitude != null && c.longitude != null && (
                    <a className="btn-secondary" href={navUrl(c.latitude, c.longitude, c.name, loc ? { lat: loc.lat, lng: loc.lng } : null)} target="_blank" rel="noreferrer">🧭 Get Directions</a>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
