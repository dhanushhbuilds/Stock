import {
  Activity, BarChart3, Brain, Briefcase, CandlestickChart, FlaskConical, LayoutDashboard, Newspaper,
  Settings, ShieldAlert, Sparkles, type LucideIcon,
} from 'lucide-react'

export interface RouteDef {
  path: string
  label: string
  icon: LucideIcon
  /** Build phase that makes this page functional. */
  phase: number
  /** Shown on the placeholder when a page is intentionally not built yet. */
  status?: string
}

export const ROUTES: RouteDef[] = [
  { path: '/', label: 'Overview', icon: LayoutDashboard, phase: 11 },
  { path: '/signal-lab', label: 'Signal Lab', icon: Sparkles, phase: 9 },
  { path: '/market', label: 'Market Data', icon: CandlestickChart, phase: 2 },
  { path: '/research', label: 'AI Research', icon: Brain, phase: 4 },
  { path: '/news', label: 'News Intelligence', icon: Newspaper, phase: 6 },
  { path: '/strategy', label: 'Strategy Lab', icon: FlaskConical, phase: 7 },
  { path: '/risk', label: 'Risk Centre', icon: ShieldAlert, phase: 8 },
  { path: '/paper', label: 'Paper Trading', icon: BarChart3, phase: 10, status: 'Postponed by the project owner.' },
  { path: '/portfolio', label: 'Portfolio', icon: Briefcase, phase: 10, status: 'Postponed with paper trading: no positions exist yet.' },
  { path: '/system', label: 'System Monitor', icon: Activity, phase: 1 },
  { path: '/settings', label: 'Settings', icon: Settings, phase: 13 },
]
