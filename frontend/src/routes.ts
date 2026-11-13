import {
  Activity, BarChart3, Brain, Briefcase, CandlestickChart, FlaskConical, LayoutDashboard, Newspaper,
  Settings, ShieldAlert, type LucideIcon,
} from 'lucide-react'

export interface RouteDef {
  path: string
  label: string
  icon: LucideIcon
  /** Build phase that makes this page functional. */
  phase: number
}

export const ROUTES: RouteDef[] = [
  { path: '/', label: 'Overview', icon: LayoutDashboard, phase: 11 },
  { path: '/market', label: 'Live Market', icon: CandlestickChart, phase: 5 },
  { path: '/research', label: 'AI Research', icon: Brain, phase: 4 },
  { path: '/news', label: 'News Intelligence', icon: Newspaper, phase: 6 },
  { path: '/strategy', label: 'Strategy Lab', icon: FlaskConical, phase: 7 },
  { path: '/risk', label: 'Risk Centre', icon: ShieldAlert, phase: 8 },
  { path: '/paper', label: 'Paper Trading', icon: BarChart3, phase: 10 },
  { path: '/portfolio', label: 'Portfolio', icon: Briefcase, phase: 10 },
  { path: '/system', label: 'System Monitor', icon: Activity, phase: 1 },
  { path: '/settings', label: 'Settings', icon: Settings, phase: 13 },
]
