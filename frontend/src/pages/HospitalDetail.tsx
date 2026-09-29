import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { get } from "../lib/api"
import { getSearchLocation } from "../lib/location"
import { Card, PageHeader, Pill, Spinner, Unavailable } from "../components/ui"
import type { Hospital } from "../lib/types"
import SimpleMap, { navUrl } from "../components/SimpleMap"
import { AppointmentDiscovery } from "./Appointments"

export default function HospitalDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [h, setH] = useState<(Hospital & { distance_km?: number | null }) | null>(null)
  const [requesting, setRequesting] = useState(false)
  const loc = getSearchLocation()

  useEffect(() => {
    const p = new URLSearchParams()
    if (loc) { p.set("lat", String(loc.lat)); p.set("lng", String(loc.lng)) }
    get<Hospital>(`/hospitals/${id}?${p}`).then(setH).catch(() => setH(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  if (!h) return <Spinner />

  return (
    <div className="space-y-6">
      <PageHeader title={h.name} subtitle={h.description} right={
        <div className="flex flex-wrap gap-2">
          <button className="btn-primary" onClick={() => setRequesting(true)}>Request Appointment</button>
          {h.latitude != null && h.longitude != null && (
            <a className="btn-secondary" href={navUrl(h.latitude, h.longitude, h.name, loc ? { lat: loc.lat, lng: loc.lng } : null)} target="_blank" rel="noreferrer">
              🧭 Get Directions
            </a>
          )}
          {h.phone && <a className="btn-secondary" href={`tel:${h.phone}`}>📞 Call</a>}
          <button className="btn-ghost" onClick={() => navigate(-1)}>← Back</button>
        </div>
      } />

      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={h.hospital_type === "Government" ? "blue" : h.hospital_type === "Private" ? "slate" : "green"}>{h.hospital_type}</Pill>
        {h.distance_km != null && <Pill tone="slate">≈ {h.distance_km} km from your search location</Pill>}
        {h.emergency_phone && <Pill tone="red">🚨 emergency line available</Pill>}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <h3 className="section-title mb-3">Departments & doctors</h3>
            {h.departments.length === 0 ? (
              <p className="muted">Department information unavailable for this facility in the current data source.</p>
            ) : (
              h.departments.map((d) => {
                const docs = h.doctors.filter((doc) => doc.department_id === d.id)
                return (
                  <div key={d.id} className="border-b border-slate-100 py-3 last:border-0">
                    <p className="font-bold">{d.name}</p>
                    {docs.length === 0 ? (
                      <p className="muted mt-1 text-sm">Doctor information unavailable for this department.</p>
                    ) : docs.map((doc) => (
                      <div key={doc.doctor_id} className="mt-1 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2">
                        <div>
                          <p className="text-sm font-semibold">{doc.name}</p>
                          <p className="text-xs text-ink-500">{doc.qualification} · {doc.designation} · OPD {doc.opd_days} {doc.consultation_hours}</p>
                        </div>
                        <Pill tone="amber">{doc.verification_status}</Pill>
                      </div>
                    ))}
                  </div>
                )
              })
            )}
            <button className="btn-primary mt-3" onClick={() => setRequesting(true)}>Request an appointment here</button>
          </Card>

          <Card>
            <h3 className="section-title mb-3">Facilities</h3>
            {(h as any).facilities?.length ? (
              <div className="flex flex-wrap gap-2">
                {(h as any).facilities.map((f: any) => (
                  <span key={f.id} className={`pill ${f.verified ? "bg-emerald-50 text-emerald-700" : "bg-slate-100"}`}>
                    {f.verified ? "✓" : ""} {f.name}
                  </span>
                ))}
              </div>
            ) : (
              <p className="muted">Facility information unavailable.</p>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <h3 className="section-title mb-2">Contact & location</h3>
            <p className="muted">{h.address || "Address information unavailable"}{h.city ? `, ${h.city}` : ""}{h.pincode ? ` — ${h.pincode}` : ""}</p>
            <p className="muted mt-1">
              ☎ {h.phone || "Information unavailable"} · Emergency: {h.emergency_phone || "Information unavailable"}
            </p>
            {h.website
              ? <a className="text-sm text-brand-700 underline" href={h.website} target="_blank" rel="noreferrer">{h.website}</a>
              : <p className="text-xs text-ink-500">Website information unavailable</p>}
            {h.latitude != null && h.longitude != null && (
              <div className="mt-3">
                <SimpleMap points={[{ id: h.id, lat: h.latitude, lng: h.longitude, label: h.name, sub: h.address }]}
                  height={240} center={loc ? [loc.lat, loc.lng] : null} zoom={loc ? 12 : 13} />
                <a className="btn-secondary mt-2 w-full" href={navUrl(h.latitude, h.longitude, h.name, loc ? { lat: loc.lat, lng: loc.lng } : null)} target="_blank" rel="noreferrer">
                  🧭 Get Directions from my location
                </a>
              </div>
            )}
          </Card>

          <Card>
            <h3 className="section-title mb-2">Live information</h3>
            <div className="space-y-2">
              <Unavailable label="Live queue status unavailable" why="no authorized live feed is connected to this hospital in the prototype." />
              <Unavailable label="Live bed availability unavailable" why="no authorized live feed is connected to this hospital in the prototype." />
              <p className="text-xs text-ink-500">
                Contact the hospital directly at {h.phone || "the listed number"} for current operational status.
                CareRoute never invents live availability.
              </p>
            </div>
          </Card>

          <Card className="!bg-slate-50">
            <h3 className="section-title mb-2">Data provenance</h3>
            <p className="text-xs text-ink-500">
              {h.data_source === "GOOGLE_PLACES_LIVE"
                ? "Identity, address and phone: live Google Places public data. Departments/doctors: not available from this source."
                : "Hospital identity, address, phone and departments: publicly verified sources."}{" "}
              Appointment requests are processed by the CareRoute hospital workflow (prototype) — this
              page does <b>not</b> claim a live connection to the hospital's own systems.
            </p>
          </Card>
        </div>
      </div>

      {requesting && (
        <AppointmentDiscovery initialHospitalId={h.id} onClose={() => setRequesting(false)}
          onBooked={() => { setRequesting(false); navigate("/app/appointments") }} />
      )}
    </div>
  )
}
