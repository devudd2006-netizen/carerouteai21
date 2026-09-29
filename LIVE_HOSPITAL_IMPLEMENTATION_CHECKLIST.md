# CareRoute AI — Live Hospital Discovery Implementation Checklist

The existing application must preserve its current UI/business logic while replacing hardcoded hospital discovery where possible.

## Required implementation

- [ ] Use device GPS coordinates as the search origin.
- [ ] Do not default to Chennai, Madurai, Nagercoil, or a specific hospital.
- [ ] Add Google Places provider only when an API key is configured.
- [ ] Search nearby hospitals/clinics dynamically.
- [ ] Display distance, address, coordinates and phone when supplied.
- [ ] Use selected coordinates for navigation.
- [ ] Keep Find Care as the central healthcare discovery feature.
- [ ] Feed the selected facility into appointment-request creation.
- [ ] Preserve patient → staff → confirmation → doctor synchronization.
- [ ] Never call CareRoute-generated appointment slots “live hospital slots.”
- [ ] Do not fabricate real doctor identities or qualifications.
- [ ] If public doctor information is unavailable, show a clear unavailable state.
- [ ] Keep controlled prototype appointment slots available as a fallback.
- [ ] Never expose or claim access to private hospital patient records.
- [ ] Keep API keys in environment variables only.
- [ ] Do not hardcode secrets into source files.
