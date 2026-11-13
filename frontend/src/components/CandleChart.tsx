import {
  CandlestickSeries, ColorType, createChart, HistogramSeries, type IChartApi, type UTCTimestamp,
} from 'lightweight-charts'
import { useEffect, useRef } from 'react'

import type { Candle } from '@/lib/api'

const css = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback

/** Candles + volume. Timestamps are shifted to IST wall-clock so the axis reads like the exchange clock. */
export function CandleChart({ candles, intraday }: { candles: Candle[]; intraday: boolean }) {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!el.current) return
    const up = css('--color-up', '#26a269')
    const down = css('--color-down', '#e0524a')
    const c = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: css('--color-muted', '#8a929e'),
        fontFamily: css('--font-mono', 'monospace'), fontSize: 11 },
      grid: { vertLines: { color: css('--color-line', '#262b33') }, horzLines: { color: css('--color-line', '#262b33') } },
      rightPriceScale: { borderColor: css('--color-line', '#262b33') },
      timeScale: { borderColor: css('--color-line', '#262b33'), timeVisible: intraday, secondsVisible: false },
      crosshair: { mode: 1 },
    })
    const s = c.addSeries(CandlestickSeries, { upColor: up, downColor: down, borderVisible: false, wickUpColor: up,
      wickDownColor: down })
    const v = c.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: 'vol' })
    c.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    const IST = 5.5 * 3600
    const t = (iso: string) => (Math.floor(new Date(iso).getTime() / 1000) + IST) as UTCTimestamp
    s.setData(candles.map((k) => ({ time: t(k.ts), open: k.open, high: k.high, low: k.low, close: k.close })))
    v.setData(candles.map((k) => ({ time: t(k.ts), value: k.volume, color: k.close >= k.open ? `${up}55` : `${down}55` })))
    c.timeScale().fitContent()
    chart.current = c
    return () => {
      c.remove()
      chart.current = null
    }
  }, [candles, intraday])

  return <div ref={el} className="h-full min-h-[320px] w-full" data-testid="candle-chart" />
}
