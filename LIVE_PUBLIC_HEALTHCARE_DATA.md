# CareRoute AI — Live Public Hospital Discovery Integration

## Purpose

CareRoute should dynamically discover nearby healthcare facilities using a legitimate public-place provider instead of a fixed Chennai/Madurai/Rajiv Gandhi hospital list.

### Public facility layer

When `VITE_GOOGLE_MAPS_API_KEY` / `GOOGLE_MAPS_API_KEY` is configured, the application may use Google Places/Maps APIs to discover:

- nearby hospitals/clinics
- hospital name
- address
- coordinates
- phone number when returned
- publicly available place details
- navigation destination

The user's current GPS coordinates are the search origin.

### Appointment layer

Google Places data is NOT treated as a live hospital appointment calendar.

CareRoute's appointment workflow remains:

Real public hospital
→ publicly available doctor information where legitimately available
→ CareRoute prototype appointment request
→ hospital staff account confirms/reschedules
→ patient sees the result
→ doctor account sees confirmed appointment

Any CareRoute-created slot must be labeled internally as prototype/demo scheduling data unless an authorized hospital scheduling integration exists.

### Doctor data

Do not fabricate real doctors, qualifications, affiliations, or appointment availability.

If public doctor data is not available from the configured provider, the UI must say that public doctor information is unavailable and allow the user to continue with hospital/department discovery.

### Data boundary

Never claim access to a hospital's private EHR, patient records, or live scheduling system unless an authorized integration exists.

### Configuration

The integration should be optional. If the Google API key is missing or the API cannot be reached, the application must continue to work using its existing controlled prototype data/provider rather than crashing.

### Required behavior

1. Ask for location once when appropriate.
2. Obtain fresh coordinates for healthcare discovery.
3. Search nearby facilities dynamically.
4. Sort by relevance/distance.
5. Selecting a facility opens its details.
6. Navigation uses the selected facility coordinates.
7. Appointment requests are stored in CareRoute's backend.
8. Staff confirmation changes the same appointment record.
9. Patient and doctor views reflect the changed record.
