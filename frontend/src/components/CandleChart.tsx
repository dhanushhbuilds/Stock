import {
  CandlestickSeries, ColorType, createChart, createSeriesMarkers, HistogramSeries, LineSeries, type SeriesMarker,
  type Time, type UTCTimestamp,
} from 'lightweight-charts'
import { useEffect, useRef } from 'react'

import type { Candle } from '@/lib/api'

export interface ChartMarker { ts: string; side: 'BUY' | 'SELL' }
export interface ChartLine { name: string; color: string; points: { ts: string; value: number | null }[] }

const IST = 5.5 * 3600
const t = (iso: string) => (Math.floor(new Date(iso).getTime() / 1000) + IST) as UTCTimestamp

/** Candles + volume (+ optional overlay lines and BUY/SELL markers). Time axis reads in IST. */
export function CandleChart({ candles, intraday, markers = [], lines = [] }: {
  candles: Candle[]
  intraday: boolean
  markers?: ChartMarker[]
  lines?: ChartLine[]
}) {
  const el = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!el.current) return
    const up = '#6fd59a'
    const down = '#ff7a6b'
    const c = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: 'rgba(235,235,245,0.55)',
        fontFamily: '-apple-system, "SF Pro Text", Inter, sans-serif', fontSize: 11, attributionLogo: false },
      grid: { vertLines: { color: 'rgba(255,255,255,0.035)' }, horzLines: { color: 'rgba(255,255,255,0.035)' } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: intraday, secondsVisible: false },
      crosshair: { mode: 1, vertLine: { color: 'rgba(255,255,255,0.25)', labelBackgroundColor: '#1c1c1e' },
        horzLine: { color: 'rgba(255,255,255,0.25)', labelBackgroundColor: '#1c1c1e' } },
    })
    const s = c.addSeries(CandlestickSeries, { upColor: up, downColor: down, borderVisible: false, wickUpColor: up,
      wickDownColor: down })
    const v = c.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: 'vol' })
    c.priceScale('vol').applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } })
    s.setData(candles.map((k) => ({ time: t(k.ts), open: k.open, high: k.high, low: k.low, close: k.close })))
    v.setData(candles.map((k) => ({ time: t(k.ts), value: k.volume, color: k.close >= k.open ? 'rgba(111,213,154,0.22)' : 'rgba(255,122,107,0.22)' })))
    for (const ln of lines) {
      const l = c.addSeries(LineSeries, { color: ln.color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false })
      l.setData(ln.points.filter((p) => p.value != null).map((p) => ({ time: t(p.ts), value: p.value as number })))
    }
    if (markers.length) {
      const ms: SeriesMarker<Time>[] = markers.map((m) => ({
        time: t(m.ts), position: m.side === 'BUY' ? 'belowBar' : 'aboveBar', color: m.side === 'BUY' ? up : down,
        shape: m.side === 'BUY' ? 'arrowUp' : 'arrowDown', size: 0.8,
      }))
      createSeriesMarkers(s, ms)
    }
    c.timeScale().fitContent()
    return () => c.remove()
  }, [candles, intraday, markers, lines])

  return <div ref={el} className="h-full min-h-[320px] w-full" data-testid="candle-chart" />
}
