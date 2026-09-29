import { useCallback, useState } from "react"
import { BrowserRouter, Routes, Route, NavLink, Link, Navigate, useLocation } from "react-router-dom"
import { AuthProvider, useAuth } from "./auth"
import { Spinner } from "./components/ui"
import { Toast, useLiveReload, useSync, useUnread } from "./lib/sync"
import Login from "./pages/Login"
import Onboarding from "./pages/Onboarding"
import UserHome from "./pages/UserHome"
import HealthMemory from "./pages/HealthMemory"
import MedicalLogs from "./pages/MedicalLogs"
import MedicationsPage from "./pages/MedicationsPage"
import Prescriptions from "./pages/Prescriptions"
import Appointments from "./pages/Appointments"
import FindCare from "./pages/FindCare"
import Hospitals from "./pages/Hospitals"
import HospitalDetail from "./pages/HospitalDetail"
import CaregiverAccess from "./pages/CaregiverAccess"
import Privacy from "./pages/Privacy"
import CommunityCare from "./pages/CommunityCare"
import MedicalCamps from "./pages/MedicalCamps"
import EmergencyPage from "./pages/EmergencyPage"
import Notifications from "./pages/Notifications"
import StaffDashboard from "./pages/StaffDashboard"
import DoctorDashboard from "./pages/DoctorDashboard"
import AdminDashboard from "./pages/AdminDashboard"
import ChwDashboard from "./pages/ChwDashboard"
import type { Role } from "./lib/types"

const NAVS: Record<string, { to: string; label: string; icon: string }[]> = {
  USER: [
    { to: "/app", label: "Home", icon: "🏠" },
    { to: "/app/logs", label: "Medical Logs", icon: "📝" },
    { to: "/app/memory", label: "Health Memory", icon: "🧠" },
    { to: "/app/medications", label: "Medications", icon: "💊" },
    { to: "/app/prescriptions", label: "Prescriptions", icon: "📄" },
    { to: "/app/appointments", label: "Appointments", icon: "📅" },
    { to: "/app/find-care", label: "Care Find", icon: "🧭" },
    { to: "/app/camps", label: "Medical Camps", icon: "⛺" },
    { to: "/app/community", label: "Community Care", icon: "🤝" },
    { to: "/app/caregivers", label: "Caregiver", icon: "👪" },
    { to: "/app/privacy", label: "Privacy", icon: "🔒" },
  ],
  CAREGIVER: [
    { to: "/app", label: "Home", icon: "🏠" },
    { to: "/app/appointments", label: "Appointments", icon: "📅" },
    { to: "/app/prescriptions", label: "Prescriptions", icon: "📄" },
    { to: "/app/medications", label: "Medications", icon: "💊" },
    { to: "/app/camps", label: "Medical Camps", icon: "⛺" },
  ],
  DOCTOR: [{ to: "/doctor", label: "My Schedule", icon: "🩺" }],
  STAFF: [{ to: "/staff", label: "Reception Desk", icon: "🛎️" }],
  ADMIN: [{ to: "/admin", label: "Administration", icon: "🏥" }],
  CHW: [{ to: "/chw", label: "Community Care", icon: "🤝" }],
}

function Shell({ children }: { children: React.ReactNode }) {
  const { me, logout, refreshMe } = useAuth()
  const nav = NAVS[me!.role] ?? []
  const loc = useLocation()
  const [toast, setToast] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)

  // Cross-dashboard live sync (four-laptop demo): one poller per signed-in session.
  const { unread, refresh: refreshUnread } = useUnread()
  const onSync = useCallback(async () => {
    const title = await refreshUnread()
    if (title) setToast(title)
    refreshMe().catch(() => undefined)
  }, [refreshUnread, refreshMe])
  useSync(onSync)
  useLiveReload(refreshUnread)

  const sideNav = (
    <nav className="flex flex-col gap-0.5 px-3 py-4">
      {nav.map((n) => (
        <NavLink key={n.to} to={n.to} onClick={() => setMenuOpen(false)}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors ${
              isActive || (n.to !== "/app" && loc.pathname.startsWith(n.to + "/"))
                ? "bg-brand-50 text-brand-700" : "text-ink-700 hover:bg-slate-100"}`}>
          <span className="w-5 text-center text-base">{n.icon}</span>
          {n.label}
        </NavLink>
      ))}
      {(me!.role === "USER" || me!.role === "CAREGIVER") && (
        <NavLink to="/app/emergency" onClick={() => setMenuOpen(false)}
          className={({ isActive }) =>
            `mt-3 flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-sm font-bold text-red-700 ${isActive ? "ring-2 ring-red-300" : ""}`}>
          <span className="w-5 text-center">🚨</span> Emergency
        </NavLink>
      )}
    </nav>
  )

  return (
    <div className="min-h-screen">
      {/* Slim top bar */}
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="flex items-center gap-3 px-4 py-2.5">
          <button className="btn-secondary !px-2.5 !py-1.5 lg:hidden" aria-label="Menu"
            onClick={() => setMenuOpen((v) => !v)}>☰</button>
          <Link to={nav[0]?.to ?? "/"} className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-base font-black text-white">C</span>
            <span className="leading-tight">
              <span className="block text-sm font-black tracking-tight">CareRoute AI</span>
              <span className="hidden text-[10px] font-medium uppercase tracking-widest text-brand-700 sm:block">One Care Journey</span>
            </span>
          </Link>
          <div className="ml-auto flex items-center gap-2.5">
            <Link to="/app/notifications" className="btn-secondary !px-3 relative" title="Notifications">🔔
              {unread > 0 && (
                <span data-testid="bell-badge" className="absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-[11px] font-black text-white">{unread}</span>
              )}
            </Link>
            <button className="btn-secondary !px-3" title="Toggle large text (elderly-friendly)"
              onClick={() => {
                const on = document.documentElement.classList.toggle("elderly")
                localStorage.setItem("cr_elderly", on ? "1" : "")
              }}>A±</button>
            <div className="text-right leading-tight">
              <p className="text-sm font-bold">{me!.name}</p>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-brand-700">{me!.role}</p>
            </div>
            <button className="btn-secondary !py-2" onClick={logout}>Sign out</button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl">
        {/* Desktop sidebar */}
        <aside className="sticky top-[57px] hidden h-[calc(100vh-57px)] w-60 shrink-0 overflow-y-auto border-r border-slate-200 bg-white lg:block">
          {sideNav}
        </aside>
        {/* Mobile drawer */}
        {menuOpen && (
          <div className="fixed inset-0 z-40 lg:hidden" onClick={() => setMenuOpen(false)}>
            <div className="absolute inset-0 bg-black/40" />
            <aside className="absolute left-0 top-0 h-full w-72 overflow-y-auto bg-white shadow-xl"
              onClick={(e) => e.stopPropagation()}>
              <div className="border-b border-slate-100 px-4 py-3 text-sm font-black">CareRoute AI</div>
              {sideNav}
            </aside>
          </div>
        )}

        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6">{children}</main>
      </div>

      <Toast message={toast} onDone={() => setToast(null)} />
      <footer className="border-t border-slate-200 py-5 text-center text-xs text-ink-500">
        CareRoute AI — prototype. Hospital identity info is publicly verified; workflow records are
        synthetic demo data. Live operational feeds are not connected.
      </footer>
    </div>
  )
}

function Home() {
  const { me } = useAuth()
  if (!me) return <Navigate to="/login" replace />
  if (me.role === "USER" && !me.onboarded) return <Navigate to="/onboarding" replace />
  const home: Record<string, string> = { USER: "/app", CAREGIVER: "/app", DOCTOR: "/doctor", STAFF: "/staff", ADMIN: "/admin", CHW: "/chw" }
  return <Navigate to={home[me.role]} replace />
}

function Guard({ roles, children }: { roles: Role[]; children: React.ReactNode }) {
  const { me, loading } = useAuth()
  if (loading) return <Spinner />
  if (!me) return <Navigate to="/login" replace />
  if (!roles.includes(me.role)) return <Navigate to="/" replace />
  if (me.role === "USER" && !me.onboarded) return <Navigate to="/onboarding" replace />
  return <Shell>{children}</Shell>
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="/" element={<Home />} />
          <Route path="/app" element={<Guard roles={["USER", "CAREGIVER"]}><UserHome /></Guard>} />
          <Route path="/app/logs" element={<Guard roles={["USER"]}><MedicalLogs /></Guard>} />
          <Route path="/app/memory" element={<Guard roles={["USER"]}><HealthMemory /></Guard>} />
          <Route path="/app/medications" element={<Guard roles={["USER", "CAREGIVER"]}><MedicationsPage /></Guard>} />
          <Route path="/app/prescriptions" element={<Guard roles={["USER", "CAREGIVER"]}><Prescriptions /></Guard>} />
          <Route path="/app/appointments" element={<Guard roles={["USER", "CAREGIVER"]}><Appointments /></Guard>} />
          <Route path="/app/find-care" element={<Guard roles={["USER", "CAREGIVER"]}><FindCare /></Guard>} />
          <Route path="/app/hospitals" element={<Guard roles={["USER", "CAREGIVER"]}><Hospitals /></Guard>} />
          <Route path="/app/hospitals/:id" element={<Guard roles={["USER", "CAREGIVER"]}><HospitalDetail /></Guard>} />
          <Route path="/app/camps" element={<Guard roles={["USER", "CAREGIVER"]}><MedicalCamps /></Guard>} />
          <Route path="/app/community" element={<Guard roles={["USER"]}><CommunityCare /></Guard>} />
          <Route path="/app/caregivers" element={<Guard roles={["USER"]}><CaregiverAccess /></Guard>} />
          <Route path="/app/privacy" element={<Guard roles={["USER"]}><Privacy /></Guard>} />
          <Route path="/app/emergency" element={<Guard roles={["USER", "CAREGIVER"]}><EmergencyPage /></Guard>} />
          <Route path="/app/notifications" element={<Guard roles={["USER", "CAREGIVER"]}><Notifications /></Guard>} />
          <Route path="/staff" element={<Guard roles={["STAFF", "ADMIN"]}><StaffDashboard /></Guard>} />
          <Route path="/doctor" element={<Guard roles={["DOCTOR"]}><DoctorDashboard /></Guard>} />
          <Route path="/admin" element={<Guard roles={["ADMIN"]}><AdminDashboard /></Guard>} />
          <Route path="/chw" element={<Guard roles={["CHW"]}><ChwDashboard /></Guard>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
