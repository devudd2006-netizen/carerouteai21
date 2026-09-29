import { MapContainer, Marker, Popup, TileLayer, useMapEvents } from "react-leaflet"
import "leaflet/dist/leaflet.css"
import L from "leaflet"

// Default Leaflet marker icons break under bundlers — pin explicit assets.
const icon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, 34],
})
const redIcon = L.icon({
  iconUrl: "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, 34],
})

export interface MapPoint {
  id: number | string
  lat: number
  lng: number
  label: string
  sub?: string
  red?: boolean
}

function ClickCatcher({ onPick }: { onPick: (lat: number, lng: number) => void }) {
  useMapEvents({
    click(e) {
      onPick(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

export default function SimpleMap({ points, height = 340, onPickLocation, center, zoom = 12 }:
  { points: MapPoint[]; height?: number; onPickLocation?: (lat: number, lng: number) => void;
    center?: [number, number] | null; zoom?: number }) {
  const c: [number, number] = center ?? (points.length ? [points[0].lat, points[0].lng] : [20.5937, 78.9629])
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200" style={{ height }}>
      <MapContainer center={c} zoom={zoom} scrollWheelZoom={false} style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {points.map((p) => (
          <Marker key={p.id} position={[p.lat, p.lng]} icon={p.red ? redIcon : icon}>
            <Popup>
              <b>{p.label}</b>
              {p.sub ? <><br />{p.sub}</> : null}
            </Popup>
          </Marker>
        ))}
        {onPickLocation && <ClickCatcher onPick={onPickLocation} />}
      </MapContainer>
    </div>
  )
}

/** Directions URL: USER/SELECTED LOCATION → SELECTED HOSPITAL (never a hard-coded route).
 *  origin optional — Google Maps uses the device location when omitted. */
export function navUrl(lat: number, lng: number, label: string, origin?: { lat: number; lng: number } | null) {
  const dest = `${lat},${lng}`
  const q = encodeURIComponent(label)
  const base = `https://www.google.com/maps/dir/?api=1&destination=${dest}&query=${q}`
  return origin ? `${base}&origin=${origin.lat},${origin.lng}` : base
}
