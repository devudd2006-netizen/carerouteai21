# CareRoute AI — Doctor/Patient Workflow Fix

## What changed

The doctor dashboard no longer behaves like a pre-populated patient directory.

A doctor can see a patient through the appointment workflow only:

1. User/patient (or authorized caregiver/CHW) requests an appointment.
2. The request is stored in the shared backend database.
3. Hospital staff receives the request.
4. Staff confirms the appointment.
5. The confirmed appointment becomes visible on the assigned doctor's dashboard.
6. The doctor opens the consultation and receives the authorized clinical snapshot for that patient.
7. The doctor can create a prescription, which is then linked to the same patient/appointment.

## Demo seed behavior

The controlled demo accounts remain available, but synthetic appointments, prescriptions, medical logs, reports, medications, conditions, allergies, and historical emergency events are no longer preloaded into the demo database.

This means an empty doctor dashboard is intentional until the demonstration creates a real workflow record.

The project still supports synthetic data when the demonstrator enters it through the application; it is not presented as real hospital patient data.

## Security behavior

Doctors only receive appointments assigned to their doctor account after hospital confirmation. Pending appointment requests remain in the hospital staff workflow.
