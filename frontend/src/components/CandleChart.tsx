import {
  AreaSeries, CandlestickSeries, ColorType, createChart, createSeriesMarkers, HistogramSeries, LineSeries, LineType,
  type SeriesMarker, type Time, type UTCTimestamp,
} from 'lightweight-charts'
import { useEffect, useRef } from 'react'

import type { Candle } from '@/lib/api'

export interface ChartMarker { ts: string; side: 'BUY' | 'SELL' }
export interface ChartLine { name: string; color: string; points: { ts: string; value: number | null }[] }

const IST = 5.5 * 3600
const t = (iso: string) => (Math.floor(new Date(iso).getTime() / 1000) + IST) as UTCTimestamp
const UP = '#30d158'
const DOWN = '#ff453a'

/** Apple-Stocks-style price chart. mode "area": smooth line coloured by the period's change with a glowing
 *  gradient; mode "candles": candlesticks. Optional overlay lines and BUY/SELL markers. Axis reads in IST. */
export function CandleChart({ candles, intraday, markers = [], lines = [], mode = 'area', height }: {
  candles: Candle[]
  intraday: boolean
  markers?: ChartMarker[]
  lines?: ChartLine[]
  mode?: 'area' | 'candles'
  height?: number
}) {
  const el = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!el.current || !candles.length) return
    const rising = candles[candles.length - 1].close >= candles[0].close
    const accent = rising ? UP : DOWN
    const c = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#6e6e73',
        fontFamily: '-apple-system, "SF Pro Text", Inter, sans-serif', fontSize: 11, attributionLogo: false },
      grid: { vertLines: { visible: false }, horzLines: { color: 'rgba(255,255,255,0.045)' } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: mode === 'area' ? 0.14 : 0.2 } },
      timeScale: { borderVisible: false, timeVisible: intraday, secondsVisible: false },
      crosshair: {
        mode: 1,
        vertLine: { color: 'rgba(255,255,255,0.35)', width: 1, style: 0, labelBackgroundColor: '#1d1d1f' },
        horzLine: { color: 'rgba(255,255,255,0.18)', width: 1, style: 2, labelBackgroundColor: '#1d1d1f' },
      },
      handleScale: { axisPressedMouseMove: false },
    })
    const main = mode === 'area'
      ? c.addSeries(AreaSeries, {
        lineColor: accent, lineWidth: 2, lineType: LineType.Curved, topColor: `${accent}55`, bottomColor: `${accent}00`,
        priceLineVisible: false, crosshairMarkerRadius: 5, crosshairMarkerBorderColor: '#000',
        crosshairMarkerBackgroundColor: accent,
      })
      : c.addSeries(CandlestickSeries, { upColor: UP, downColor: DOWN, borderVisible: false, wickUpColor: UP,
        wickDownColor: DOWN, priceLineVisible: false })
    if (mode === 'area') {
      main.setData(candles.map((k) => ({ time: t(k.ts), value: k.close })))
    } else {
      main.setData(candles.map((k) => ({ time: t(k.ts), open: k.open, high: k.high, low: k.low, close: k.close })))
    }
    const v = c.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: 'vol', lastValueVisible: false,
      priceLineVisible: false })
    c.priceScale('vol').applyOptions({ scaleMargins: { top: 0.88, bottom: 0 } })
    v.setData(candles.map((k) => ({ time: t(k.ts), value: k.volume, color: 'rgba(255,255,255,0.10)' })))
    for (const ln of lines) {
      const l = c.addSeries(LineSeries, { color: ln.color, lineWidth: 1, lineStyle: 2, priceLineVisible: false,
        lastValueVisible: false, crosshairMarkerVisible: false })
      l.setData(ln.points.filter((p) => p.value != null).map((p) => ({ time: t(p.ts), value: p.value as number })))
    }
    if (markers.length) {
      const ms: SeriesMarker<Time>[] = markers.map((m) => ({
        time: t(m.ts), position: m.side === 'BUY' ? 'belowBar' : 'aboveBar', color: m.side === 'BUY' ? '#ffffff' : '#8e8e93',
        shape: m.side === 'BUY' ? 'arrowUp' : 'arrowDown', size: 0.7,
      }))
      createSeriesMarkers(main, ms)
    }
    c.timeScale().fitContent()
    return () => c.remove()
  }, [candles, intraday, markers, lines, mode])

  return <div ref={el} className="h-full w-full" style={{ minHeight: height ?? 320 }} data-testid="candle-chart" />
}
