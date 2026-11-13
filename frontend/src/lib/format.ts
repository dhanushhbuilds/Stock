export const pct = (x: number | null | undefined, digits = 1) =>
  x == null || Number.isNaN(x) ? '—' : `${(x * 100).toFixed(digits)}%`

export const num = (x: number | null | undefined, digits = 2) =>
  x == null || Number.isNaN(x) ? '—' : x.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })

export const int = (x: number | null | undefined) => (x == null ? '—' : Math.round(x).toLocaleString('en-IN'))

export const signed = (x: number | null | undefined, digits = 3) =>
  x == null ? '—' : `${x >= 0 ? '+' : ''}${x.toFixed(digits)}`

export const dateTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' }) : '—'

export const shortDate = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString('en-IN', { dateStyle: 'medium', timeZone: 'Asia/Kolkata' }) : '—'

/** Colour class for a value that is good when positive. */
export const tone = (x: number | null | undefined) =>
  x == null ? 'text-muted' : x > 0 ? 'text-up' : x < 0 ? 'text-down' : 'text-muted'
