// CareRoute AI — shared session location service.
//
// One source of truth for "where is the user searching from":
//  • requested ONCE per session (§20 — no repeated permission prompts),
//  • shared by Hospitals, Care Find, Appointments discovery, Emergency and Camps,
//  • carries GPS accuracy so the UI can warn when the fix is poor (§3),
//  • manual search geocodes via the public Nominatim service (no key required).
//    If the geocoder is unreachable the search FAILS HONESTLY — it never
//    silently resolves to a hard-coded city.

import { useEffect, useState } from "react"

export interface SearchLocation {
  lat: number
  lng: number
  label: string
  source: "device" | "manual"
  accuracy_m?: number | null
}

type Status = "idle" | "locating" | "granted" | "manual" | "denied"

const SESSION_KEY = "cr_search_location"

function hydrate(): SearchLocation | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    return raw ? (JSON.parse(raw) as SearchLocation) : null
  } catch { return null }
}

let cached: SearchLocation | null = hydrate()
const listeners = new Set<() => void>()

export function getSearchLocation(): SearchLocation | null { return cached }

export function setSearchLocation(loc: SearchLocation | null) {
  cached = loc
  try {
    if (loc) sessionStorage.setItem(SESSION_KEY, JSON.stringify(loc))
    else sessionStorage.removeItem(SESSION_KEY)
  } catch { /* private mode */ }
  listeners.forEach((f) => f())
}

export interface DeviceFix { lat: number; lng: number; accuracy_m: number | null }

/** Real device coordinates via the Geolocation API (§2). */
export function getCurrentPosition(timeoutMs = 15000): Promise<DeviceFix> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("unsupported"))
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const fix = {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy_m: pos.coords.accuracy != null ? Math.round(pos.coords.accuracy) : null,
        }
        console.log(`[location] device fix: lat=${fix.lat} lng=${fix.lng} accuracy=${fix.accuracy_m}m`)
        resolve(fix)
      },
      (err) => reject(err),
      { timeout: timeoutMs, maximumAge: 0, enableHighAccuracy: true })
  })
}

// ------------------------------------------------------------- geocoding
const NOMINATIM = "https://nominatim.openstreetmap.org"

export async function geocode(text: string): Promise<SearchLocation | null> {
  const q = text.trim()
  if (!q) return null
  try {
    const r = await fetch(
      `${NOMINATIM}/search?format=json&limit=1&q=${encodeURIComponent(q)}`,
      { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(6000) })
    if (r.ok) {
      const rows = await r.json()
      if (rows?.length) {
        const hit = rows[0]
        const label = String(hit.display_name ?? q).split(",").slice(0, 3).join(", ")
        console.log(`[location] geocoded "${q}" → ${hit.lat}, ${hit.lon}`)
        return { lat: parseFloat(hit.lat), lng: parseFloat(hit.lon), label, source: "manual" }
      }
      return null // geocoder reachable but no match — honest failure
    }
  } catch { /* network unavailable */ }
  return null // §1: NO silent fallback to a hard-coded city
}

export async function reverseLabel(lat: number, lng: number): Promise<string> {
  try {
    const r = await fetch(
      `${NOMINATIM}/reverse?format=json&zoom=13&lat=${lat}&lon=${lng}`,
      { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(5000) })
    if (r.ok) {
      const j = await r.json()
      const a = j?.address ?? {}
      // Prefer the actual district/town hierarchy over stale-looking suburb
      // labels. This is what the UI displays beside "Using your current location".
      const area = a.village || a.town || a.city || a.municipality || a.county || a.suburb || a.neighbourhood
      const district = a.state_district || a.district || a.county
      const state = a.state
      if (area) {
        const parts = [area, district, state].filter(Boolean).map(String)
        return Array.from(new Set(parts)).slice(0, 3).join(", ")
      }
      if (j?.display_name) return String(j.display_name).split(",").slice(0, 3).join(", ")
    }
  } catch { /* fall through */ }
  return `${lat.toFixed(4)}, ${lng.toFixed(4)}`
}

// ------------------------------------------------------------------- hook
export function useSearchLocation(autoRefresh = false) {
  const [loc, setLoc] = useState<SearchLocation | null>(cached)
  const [status, setStatus] = useState<Status>(cached ? (cached.source === "device" ? "granted" : "manual") : "idle")
  const [accuracyNote, setAccuracyNote] = useState<string | null>(null)

  useEffect(() => {
    const fn = () => {
      setLoc(cached)
      if (cached) setStatus(cached.source === "device" ? "granted" : "manual")
    }
    listeners.add(fn)
    return () => { listeners.delete(fn) }
  }, [])

  // A granted permission does not require another prompt. Refreshing the fix
  // is therefore safe and keeps CareRoute genuinely location-aware when a user
  // moves between searches/pages.
  useEffect(() => {
    if (!autoRefresh) return
    useMyLocation().catch(() => undefined)
    // Permission state is handled by the browser; this is a fresh position read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh])

  const applyAccuracy = (acc: number | null) => {
    if (acc != null && acc > 2000) {
      setAccuracyNote(`Your location is approximate (±${Math.round(acc / 1000)} km). Search results may be less accurate.`)
    } else if (acc != null) {
      setAccuracyNote(`Location accuracy: approximately ${acc} metres`)
    } else {
      setAccuracyNote(null)
    }
  }

  const useMyLocation = async (): Promise<boolean> => {
    setStatus("locating")
    setAccuracyNote(null)
    try {
      const fix = await getCurrentPosition()
      const label = await reverseLabel(fix.lat, fix.lng)
      setSearchLocation({ lat: fix.lat, lng: fix.lng, label, source: "device", accuracy_m: fix.accuracy_m })
      applyAccuracy(fix.accuracy_m)
      setStatus("granted")
      return true
    } catch {
      setStatus("denied")
      return false
    }
  }

  const searchManual = async (text: string): Promise<boolean> => {
    const g = await geocode(text)
    if (!g) return false
    setSearchLocation(g)
    setAccuracyNote(null)
    setStatus("manual")
    return true
  }

  const clear = () => { setSearchLocation(null); setStatus("idle"); setAccuracyNote(null) }

  return { loc, status, accuracyNote, useMyLocation, searchManual, clear }
}
