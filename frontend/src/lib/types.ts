export type Role = "USER" | "CAREGIVER" | "DOCTOR" | "STAFF" | "ADMIN" | "CHW"

export interface Me {
  id: number
  role: Role
  name: string
  phone?: string
  worker_id?: string
  onboarded: boolean
  mfa_enabled: boolean
  device_unlock_enabled?: boolean
  patient_id?: number | null
  doctor?: {
    id: number
    name: string
    speciality_key: string
    qualification: string
    designation: string
    hospital_ids: number[]
  } | null
  staff_hospital_id?: number | null
  admin_hospital_id?: number | null
  chw_id?: number | null
}

export interface Hospital {
  id: number
  name: string
  hospital_type: string
  address: string
  city: string
  pincode: string
  latitude: number
  longitude: number
  phone: string
  emergency_phone: string
  website: string
  description: string
  data_source: string
  verified_fields: Record<string, boolean>
  distance_km?: number | null
  /** Live Places discovery fields (present when data_source is GOOGLE_PLACES_LIVE). */
  place_id?: string
  public_rating?: number | null
  public_rating_count?: number | null
  open_now?: boolean | null
  departments: { id: number; name: string; speciality_key: string; description: string }[]
  doctors: DoctorRow[]
  facilities?: { id: number; name: string; category: string; verified: boolean }[]
}

export interface DoctorRow {
  doctor_id: number
  name: string
  qualification: string
  speciality_key: string
  designation: string
  years_experience: number
  verification_status: string
  profile_note: string
  department_id?: number
  department_name?: string | null
  hospital_id?: number
  hospital_name?: string
  opd_days?: string
  consultation_hours?: string
  speciality_label?: string
}

export interface Appointment {
  id: number
  patient_id: number
  patient_name: string
  doctor_id: number
  doctor_name: string
  speciality_key: string
  hospital_id: number
  hospital_name: string
  department: string
  appointment_date: string
  time_slot: string
  status: "REQUESTED" | "CONFIRMED" | "REJECTED" | "RESCHEDULED" | "RESCHEDULED_MOVED" | "COMPLETED"
  reason: string
  staff_note: string | null
  token_number: string | null
  requested_on_behalf: string
}

export interface Caregiver {
  relationship_id: number
  caregiver_name: string
  caregiver_phone: string
  relationship: string
  status: string
  permissions: Record<string, boolean>
  recent_access: { action: string; at: string; result: string }[]
}

export const CAREGIVER_PERMS: { key: string; label: string }[] = [
  { key: "view_appointments", label: "View appointments" },
  { key: "request_appointments", label: "Request appointments" },
  { key: "view_prescriptions", label: "View authorized prescriptions" },
  { key: "view_medications", label: "View medication information" },
  { key: "view_health_logs", label: "View daily health logs" },
  { key: "assist_medication", label: "Assist with medication" },
  { key: "assist_navigation", label: "Assist with navigation" },
  { key: "emergency_assist", label: "Emergency assistance" },
  { key: "contact_emergency_person", label: "Contact emergency person" },
]

export interface Notification {
  id: number
  type: string
  title: string
  body: string
  read: boolean
  created_at: string
}
