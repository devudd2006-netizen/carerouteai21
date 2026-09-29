"""CareRoute AI — HospitalDataProvider abstraction.

The application always talks to a provider interface. Today the
PrototypeHospitalProvider serves controlled demonstration data. When an authorized
hospital integration (e.g. HL7 FHIR R4 endpoint) exists, an AuthorizedHospitalProvider
can implement the same interface without frontend redesign.

Live operational data (beds, queues, doctor availability, ambulance ETA) is NEVER
fabricated: providers report it as unavailable when no genuine source exists.
"""
from abc import ABC, abstractmethod
import os
import time

import httpx
from sqlalchemy.orm import Session

from models import DataSource, Doctor, DoctorHospitalAffiliation, Hospital


class HospitalDataProvider(ABC):
    name: str

    @abstractmethod
    def list_hospitals(self, db: Session) -> list[dict]: ...

    @abstractmethod
    def hospital_detail(self, db: Session, hospital_id: int) -> dict | None: ...

    @abstractmethod
    def live_availability(self, db: Session, hospital_id: int, kind: str) -> dict:
        """kind: queue | beds | doctor_slots | ambulance. Never invent values."""

    @abstractmethod
    def integration_status(self) -> dict: ...


class PrototypeHospitalProvider(HospitalDataProvider):
    """Serves the controlled demo dataset stored in the CareRoute database."""
    name = "PrototypeHospitalProvider"

    def list_hospitals(self, db: Session) -> list[dict]:
        hospitals = db.query(Hospital).all()
        return [self.hospital_detail(db, h.id) for h in hospitals]

    def hospital_detail(self, db: Session, hospital_id: int) -> dict | None:
        h = db.query(Hospital).filter(Hospital.id == hospital_id).first()
        if not h:
            return None
        affs = db.query(DoctorHospitalAffiliation, Doctor).join(
            Doctor, DoctorHospitalAffiliation.doctor_id == Doctor.id).filter(
            DoctorHospitalAffiliation.hospital_id == hospital_id).all()
        return {
            "id": h.id, "name": h.name, "hospital_type": h.hospital_type,
            "address": h.address, "city": h.city, "pincode": h.pincode,
            "latitude": h.latitude, "longitude": h.longitude,
            "phone": h.phone, "emergency_phone": h.emergency_phone, "website": h.website,
            "description": h.description,
            "data_source": h.data_source,
            "verified_fields": h.verified_fields or {},
            "departments": [{"id": d.id, "name": d.name, "speciality_key": d.speciality_key,
                             "description": d.description} for d in h.departments],
            "doctors": [{
                "doctor_id": doc.id, "name": doc.name, "qualification": doc.qualification,
                "speciality_key": doc.speciality_key, "designation": doc.designation,
                "years_experience": doc.years_experience,
                "verification_status": doc.verification_status,
                "profile_note": doc.profile_note,
                "department_id": aff.department_id,
                "opd_days": aff.opd_days, "consultation_hours": aff.consultation_hours,
            } for aff, doc in affs],
        }

    def live_availability(self, db: Session, hospital_id: int, kind: str) -> dict:
        # Honest unavailable state — the prototype has no live hospital feed.
        return {"kind": kind, "available": False, "state": "LIVE_UNAVAILABLE",
                "message": "Live availability unavailable — no authorized live feed connected.",
                "provider": self.name}

    def integration_status(self) -> dict:
        return {"provider": self.name, "mode": "PROTOTYPE",
                "future": ["AuthorizedHospitalProvider via HL7 FHIR R4",
                           "Official emergency services integration"]}


class AuthorizedHospitalProvider(HospitalDataProvider):
    """Reserved for future authorized hospital integrations. Intentionally inert."""
    name = "AuthorizedHospitalProvider"

    def list_hospitals(self, db: Session) -> list[dict]:
        return []

    def hospital_detail(self, db: Session, hospital_id: int) -> dict | None:
        return None

    def live_availability(self, db: Session, hospital_id: int, kind: str) -> dict:
        return {"kind": kind, "available": False, "state": "NOT_CONFIGURED",
                "message": "No authorized hospital integration is configured.",
                "provider": self.name}

    def integration_status(self) -> dict:
        return {"provider": self.name, "mode": "PLANNED", "future": []}


# ---------------------------------------------------------------- Places API
# Master prompt §3/§26/§45: when GOOGLE_MAPS_API_KEY is configured, dynamic hospital
# discovery uses the Google Places API (live, publicly available place information).
# Without a key the application falls back to the verified prototype directory —
# it never pretends a live provider is connected.
_PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
_PLACES_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
_PLACES_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.location,"
    "places.rating,places.userRatingCount,places.websiteUri,places.internationalPhoneNumber,"
    "places.primaryType,places.types,places.currentOpeningHours.openNow"
)


class PlacesUnavailableError(RuntimeError):
    """Raised when the Places provider is active but the live call fails."""


# -------------------------------------------------- Overpass (OpenStreetMap)
# A legitimate, keyless public source of real healthcare place data:
# OpenStreetMap's Overpass API carries mapped hospitals/clinics (amenity=hospital,
# amenity=doctors, healthcare=hospital/centre...) worldwide. This makes discovery
# GENUINELY location-aware with zero configuration — REAL results for ANY
# coordinates, with no hard-coded city or hospital and no API key required.
# When GOOGLE_MAPS_API_KEY is configured, GooglePlacesProvider takes precedence.
_OVERPASS_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
_OVERPASS_MIRRORS = [
    _OVERPASS_URL,
    os.environ.get("OVERPASS_MIRROR", "https://overpass.kumi.systems/api/interpreter"),
]
_OVERPASS_TIMEOUT = float(os.environ.get("OVERPASS_TIMEOUT", "15"))
# Short-TTL cache: identical nearby searches within a few minutes reuse the live
# result. This keeps the demo burst-friendly and respects the public API's
# fair-use limits (429) without ever inventing data.
_OVERPASS_CACHE_TTL = float(os.environ.get("OVERPASS_CACHE_TTL", "300"))
_overpass_cache: dict[str, tuple[float, dict]] = {}


class OverpassProvider(HospitalDataProvider):
    """Real nearby healthcare search over OpenStreetMap via the Overpass API.

    Pipeline (master prompt §2/§3): DEVICE GPS → lat/lng → Overpass query around
    those coordinates → real mapped healthcare facilities → distance ranking.
    Only fields genuinely present in OSM are returned; everything missing is
    None and the UI shows "Information unavailable" — nothing is invented.
    """
    name = "OverpassProvider"

    def __init__(self, api_key: str = ""):
        self.api_key = ""  # keyless by design; signature parity with GooglePlacesProvider

    # -- HospitalDataProvider contract (directory-style calls are not applicable)
    def list_hospitals(self, db: Session) -> list[dict]:
        raise PlacesUnavailableError(
            "Live nearby search needs coordinates — use the location-aware search.")

    def hospital_detail(self, db: Session, hospital_id: int) -> dict | None:
        return None

    def live_availability(self, db: Session, hospital_id: int, kind: str) -> dict:
        return {"kind": kind, "available": False, "state": "LIVE_UNAVAILABLE",
                "message": "Live availability unavailable — OSM provides mapped place "
                           "information, not live operational feeds.",
                "provider": self.name}

    def integration_status(self) -> dict:
        return {"provider": self.name, "mode": "LIVE_NEARBY_SEARCH",
                "data_source": "OPENSTREETMAP_OVERPASS",
                "future": ["Google Places (set GOOGLE_MAPS_API_KEY)",
                           "AuthorizedHospitalProvider via HL7 FHIR R4"]}

    # ------------------------------------------------ the real search
    def search_nearby_hospitals(self, latitude: float, longitude: float,
                               radius_m: int, filters: dict | None = None) -> dict:
        """Returns {status, results, count}. status: ok | empty | failed.

        Dev logging per master prompt §6: request params + HTTP status + result
        count. Never logs API keys (there are none) and never fabricates rows.
        """
        filters = filters or {}
        emergency_only = bool(filters.get("emergency"))
        speciality = (filters.get("speciality") or "").strip().lower()
        # Overpass QL: healthcare amenities within radius of the coordinates.
        # Emergency filter keeps 24/7 emergency-capable mapped facilities.
        emerg_clause = '["emergency"]' if emergency_only else ""
        q = (
            f"[out:json][timeout:{int(_OVERPASS_TIMEOUT)}];"
            f"(nwr[~'^(amenity|healthcare)$'~'^(hospital|clinic|doctors|centre)$']"
            f"(around:{radius_m},{latitude},{longitude});"
            f"nwr[amenity=hospital]{emerg_clause}(around:{radius_m},{latitude},{longitude}););"
            f"out center {int(filters.get('limit', 40))};"
        )
        # Cache lookup on a ~100 m grid so tiny coordinate drift still hits.
        cache_key = f"{round(latitude, 3)}:{round(longitude, 3)}:{radius_m}:{emergency_only}:{speciality}"
        cached = _overpass_cache.get(cache_key)
        if cached and (time.time() - cached[0]) < _OVERPASS_CACHE_TTL:
            print(f"[HealthcarePlacesProvider] CACHE HIT {cache_key} "
                  f"count={cached[1]['count']}")
            return cached[1]

        last_error: Exception | None = None
        for url in _OVERPASS_MIRRORS:
            try:
                print(f"[HealthcarePlacesProvider] REQUEST lat={latitude} lng={longitude} "
                      f"radius_m={radius_m} emergency={emergency_only} url={url}")
                resp = httpx.post(url, data={"data": q}, timeout=_OVERPASS_TIMEOUT,
                                  headers={"User-Agent": "CareRouteAI-Prototype/1.0 (academic demo)"})
                print(f"[HealthcarePlacesProvider] RESPONSE http={resp.status_code} from {url}")
                resp.raise_for_status()
                elements = resp.json().get("elements", [])
                results = [self._element_to_place(e) for e in elements]
                results = [r for r in results if r["name"]]
                if speciality:
                    results = self._filter_for_speciality(results, speciality)
                print(f"[HealthcarePlacesProvider] RESULTS count={len(results)}")
                out = {"status": "ok" if results else "empty", "results": results,
                       "count": len(results)}
                _overpass_cache[cache_key] = (time.time(), out)
                return out
            except Exception as exc:  # network down, timeout, rate limit → try mirror
                last_error = exc
                print(f"[HealthcarePlacesProvider] FAILED via {url}: "
                      f"{type(exc).__name__}: {exc}")
        return {"status": "failed", "results": [], "count": 0,
                "error": f"{type(last_error).__name__}" if last_error else "unknown"}

    @staticmethod
    def _filter_for_speciality(results: list[dict], speciality: str) -> list[dict]:
        """Keep live map results relevant to the requested care category.

        OSM often lacks department metadata, so we use only publicly mapped
        specialty/name/type signals. A specialty request must never return an
        obviously unrelated clinic (e.g. an eye clinic for orthopaedics).
        General hospitals are retained as a secondary option because their
        departments are frequently not mapped in OSM.
        """
        groups = {
            "orthopaedics": {"orthopaed", "orthopedic", "orthopaedic", "ortho", "bone", "joint", "trauma"},
            "ophthalmology": {"eye", "ophthalm", "vision", "optical", "optometry"},
            "cardiology": {"cardio", "cardiac", "heart"},
            "urology": {"urolog", "urinary", "kidney", "renal"},
            "ent": {"ent", "ear", "nose", "throat", "otolaryng"},
            "dermatology": {"dermat", "skin"},
            "oncology": {"oncolog", "cancer"},
            "obstetrics_gynaecology": {"gyn", "obstet", "maternity", "women"},
            "general_medicine": {"general medicine", "general hospital", "multispecial", "multi-special"},
            "emergency": {"emergency", "trauma"},
        }
        terms = groups.get(speciality, set())
        if not terms:
            return results
        matches, general = [], []
        unrelated_facility_terms = {
            "ophthalmology": {"eye", "ophthalm", "vision", "optical", "optometry"},
            "orthopaedics": {"eye", "ophthalm", "optical", "dental", "dentist"},
            "cardiology": {"eye", "ophthalm", "dental"},
            "urology": {"eye", "ophthalm", "dental"},
        }
        unrelated = unrelated_facility_terms.get(speciality, set())
        for r in results:
            text = " ".join(str(r.get(k) or "") for k in ("name", "address", "city", "description", "specialties")).lower()
            htype = (r.get("hospital_type") or "").lower()
            if any(t in text for t in terms):
                matches.append(r)
            elif htype == "hospital" and not any(t in text for t in unrelated):
                general.append(r)
        # If mapped specialty evidence exists, never dilute it with unrelated clinics.
        if matches:
            return matches + general[:8]
        # No specialty metadata: show only actual hospitals, not arbitrary clinics/doctors.
        return general

    @staticmethod
    def _element_to_place(e: dict) -> dict:
        """Map an OSM element to the shared hospital-result shape.
        Coordinates: node → lat/lon; way/relation → computed center ("center")."""
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lng = e.get("lon") or (e.get("center") or {}).get("lon")
        t = e.get("tags", {})
        # Honest type mapping: is it a hospital or a smaller facility?
        amenity = t.get("amenity", "")
        healthcare = t.get("healthcare", "")
        if amenity == "hospital" or "hospital" in healthcare:
            htype = "Hospital"
        elif amenity == "clinic" or "clinic" in healthcare:
            htype = "Clinic"
        else:
            htype = "Doctor"
        phone = t.get("phone") or t.get("contact:phone") or ""
        mapped_specialty = t.get("healthcare:speciality") or t.get("speciality") or t.get("healthcare:specialty") or ""
        emergency = t.get("emergency") not in (None, "no")
        return {
            "place_id": f"osm/{e.get('type')}/{e.get('id')}",
            "name": t.get("name", ""),
            "hospital_type": htype,
            "address": " ".join(x for x in [t.get("addr:housenumber"), t.get("addr:street")] if x) or None,
            "city": t.get("addr:city") or t.get("addr:suburb") or None,
            "pincode": t.get("addr:postcode") or "",
            "latitude": lat, "longitude": lng,
            "phone": phone, "emergency_phone": phone if emergency else "",
            "website": t.get("website") or t.get("contact:website") or "",
            "description": f"Mapped healthcare facility (OpenStreetMap) — {htype}. {mapped_specialty}".strip(),
            "data_source": "OPENSTREETMAP_OVERPASS",
            "verified_fields": {"name": True, "location": True,
                                "phone": bool(phone), "address": bool(t.get("addr:street"))},
            "public_rating": None,   # OSM has no ratings — never invented
            "public_rating_count": None,
            "open_now": None,        # OSM opening_hours parsing is unreliable — honest None
            "osm_id": e.get("id"),
            "osm_type": e.get("type"),
            "emergency_capability": emergency,
            "specialties": ([mapped_specialty] if mapped_specialty else []) + (["emergency"] if emergency and htype == "Hospital" else []),
            "departments": [],       # OSM has no department data — never invented
            "doctors": [],           # OSM has no practitioner data — never invented
        }


class GooglePlacesProvider(HospitalDataProvider):
    """Dynamic location-based hospital discovery via the Google Places API.

    Returns genuinely live public place data (name, address, coordinates, phone,
    website, public rating, open-now). Always transparent: responses carry the
    data source. A network/key failure raises PlacesUnavailableError so the API
    layer can fall back gracefully to the verified prototype directory.
    """
    name = "GooglePlacesProvider"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _headers(self, field_mask: str) -> dict:
        return {"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": field_mask}

    @staticmethod
    def _error_note() -> str:
        return ("Live Google Places data unavailable right now — showing the verified "
                "prototype hospital directory instead.")

    def _search_nearby(self, lat: float, lng: float, radius_m: int = 5000) -> list[dict] | None:
        body = {"includedTypes": ["hospital"], "maxResultCount": 20,
                "locationRestriction": {"circle": {
                    "center": {"latitude": lat, "longitude": lng}, "radius": radius_m}}}
        try:
            r = httpx.post(_PLACES_SEARCH_URL, headers=self._headers(_PLACES_FIELD_MASK),
                           json=body, timeout=10)
            r.raise_for_status()
            return r.json().get("places", [])
        except Exception:
            return None

    def _search_text(self, query: str, lat: float | None, lng: float | None) -> list[dict] | None:
        body: dict = {"textQuery": query, "includedType": "hospital",
                      "maxResultCount": 20, "regionCode": "IN"}
        if lat is not None and lng is not None:
            body["locationBias"] = {"circle": {
                "center": {"latitude": lat, "longitude": lng}, "radius": 5000}}
        try:
            r = httpx.post(_PLACES_TEXT_URL, headers=self._headers(_PLACES_FIELD_MASK),
                           json=body, timeout=10)
            r.raise_for_status()
            return r.json().get("places", [])
        except Exception:
            return None

    def _search_text_general(self, query: str, lat: float, lng: float, radius_m: int = 15000) -> list[dict] | None:
        """Public place search without forcing the result type to hospital.

        Used for location-aware community resources such as medical camps. The
        caller filters the results and never treats a generic place as a medical
        camp unless its public name/address actually supports that description.
        """
        body: dict = {"textQuery": query, "maxResultCount": 20, "regionCode": "IN",
                      "locationBias": {"circle": {
                          "center": {"latitude": lat, "longitude": lng}, "radius": radius_m}}}
        try:
            r = httpx.post(_PLACES_TEXT_URL, headers=self._headers(_PLACES_FIELD_MASK),
                           json=body, timeout=10)
            r.raise_for_status()
            return r.json().get("places", [])
        except Exception:
            return None

    @staticmethod
    def _place_to_hospital(p: dict) -> dict:
        loc = p.get("location") or {}
        ptype = p.get("primaryType") or "hospital"
        addr = p.get("formattedAddress", "")
        return {
            "place_id": p.get("id"),
            "name": (p.get("displayName") or {}).get("text", ""),
            "hospital_type": ptype.replace("_", " ").title() if ptype else "Hospital",
            "address": addr,
            "city": addr.split(",")[-2].strip() if addr.count(",") >= 1 else "",
            "pincode": addr.split(",")[-1].strip() if addr else "",
            "latitude": loc.get("latitude"), "longitude": loc.get("longitude"),
            "phone": p.get("internationalPhoneNumber", ""),
            "emergency_phone": "",
            "website": p.get("websiteUri", ""),
            "description": "Live public place information from Google Places.",
            "data_source": "GOOGLE_PLACES_LIVE",
            "verified_fields": {"name": True, "address": True, "location": True,
                                "phone": bool(p.get("internationalPhoneNumber")),
                                "website": bool(p.get("websiteUri"))},
            "public_rating": p.get("rating"),
            "public_rating_count": p.get("userRatingCount"),
            "open_now": p.get("currentOpeningHours", {}).get("openNow"),
            "departments": [],  # Places has no clinical department data — never invented
            "doctors": [],      # Places has no practitioner data — never invented
        }

    def list_hospitals(self, db: Session) -> list[dict]:
        raise PlacesUnavailableError(self._error_note())

    def hospital_detail(self, db: Session, hospital_id: int) -> dict | None:
        return None  # Places results carry full detail inline; local ids don't apply.

    def live_availability(self, db: Session, hospital_id: int, kind: str) -> dict:
        return {"kind": kind, "available": False, "state": "LIVE_UNAVAILABLE",
                "message": "Live availability unavailable — Google Places provides public "
                           "place information, not live operational feeds.",
                "provider": self.name}

    def integration_status(self) -> dict:
        return {"provider": self.name, "mode": "LIVE_DISCOVERY",
                "data_source": "GOOGLE_PLACES_LIVE",
                "future": ["AuthorizedHospitalProvider via HL7 FHIR R4"]}


def get_provider(db: Session) -> HospitalDataProvider:
    """Selects the active provider from configuration (env-overridable).

    Priority: authorized integration → Google Places (if key configured) →
    OpenStreetMap Overpass (real, keyless) → CAREROUTE_PROVIDER=prototype opts
    into the seeded demo directory (development/demo use ONLY — never an
    automatic fallback for user searches).
    """
    from config import settings
    if os.environ.get("CAREROUTE_PROVIDER") == "authorized":
        return AuthorizedHospitalProvider()
    if settings.GOOGLE_MAPS_API_KEY:
        return GooglePlacesProvider(settings.GOOGLE_MAPS_API_KEY)
    if os.environ.get("CAREROUTE_PROVIDER") == "prototype":
        row = db.query(DataSource).filter(DataSource.provider_type == "PROTOTYPE",
                                          DataSource.status == "CONNECTED").first()
        return PrototypeHospitalProvider()
    return OverpassProvider()
