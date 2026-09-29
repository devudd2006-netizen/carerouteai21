import { createContext, useContext, useEffect, useState, useCallback } from "react"
import type { ReactNode } from "react"
import { api, get, post, setTokens, clearTokens, tokens } from "./lib/api"
import type { Me, Role } from "./lib/types"

interface AuthState {
  me: Me | null
  loading: boolean
  loginWithOtp: (identifier: string, code: string) => Promise<Me>
  requestOtp: (identifier: string) => Promise<{ demo_otp: string; message: string }>
  logout: () => Promise<void>
  refreshMe: () => Promise<void>
  switchDemoRole: (role: Role) => Promise<void>
}

const Ctx = createContext<AuthState>(null as any)
export const useAuth = () => useContext(Ctx)

const DEMO_IDS: Record<string, string> = {
  USER: "+919840000001",
  CAREGIVER: "+919840000002",
  DOCTOR: "DOC101",
  STAFF: "STF201",
  ADMIN: "ADM001",
  CHW: "CHW042",
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshMe = useCallback(async () => {
    try {
      const data = await get<Me>("/auth/me")
      setMe(data)
    } catch {
      setMe(null)
    }
  }, [])

  useEffect(() => {
    (async () => {
      if (tokens().access) await refreshMe()
      setLoading(false)
    })()
  }, [refreshMe])

  const requestOtp = useCallback(async (identifier: string) => {
    return post<{ demo_otp: string; message: string }>("/auth/request-otp", { identifier })
  }, [])

  const loginWithOtp = useCallback(async (identifier: string, code: string) => {
    const data = await post<any>("/auth/verify-otp", { identifier, code })
    setTokens(data.access_token, data.refresh_token)
    setMe(data.user)
    return data.user as Me
  }, [])

  const logout = useCallback(async () => {
    const { refresh } = tokens()
    try {
      if (refresh) await post("/auth/logout", { refresh_token: refresh })
    } catch { /* ignore */ }
    clearTokens()
    setMe(null)
  }, [])

  const switchDemoRole = useCallback(async (role: Role) => {
    const identifier = DEMO_IDS[role]
    const { demo_otp } = await requestOtp(identifier)
    await loginWithOtp(identifier, demo_otp)
  }, [requestOtp, loginWithOtp])

  return (
    <Ctx.Provider value={{ me, loading, loginWithOtp, requestOtp, logout, refreshMe, switchDemoRole }}>
      {children}
    </Ctx.Provider>
  )
}

// Role helpers used across dashboards
export const isPatientSide = (role?: Role) => role === "USER" || role === "CAREGIVER"
export async function safeGet<T>(path: string, fallback: T): Promise<T> {
  try {
    return await get<T>(path)
  } catch (e: any) {
    if (e?.status === 403) return fallback
    throw e
  }
}
export { api }
