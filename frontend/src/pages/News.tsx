import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { PageHeader } from '@/components/PageHeader'
import { Badge, Button, Note, Panel, QueryState, Table } from '@/components/ui'
import { apiGet, apiPost, type NewsRow } from '@/lib/api'
import { dateTime, pct, signed, tone } from '@/lib/format'

const SOURCES = [
  ['nse_announcements', 'NSE announcements'],
  ['rbi_press', 'RBI press releases'],
  ['sebi', 'SEBI'],
] as const

interface IngestStats {
  received: number
  inserted: number
  duplicates: number
  near_duplicates: number
  mapped_to_instrument: number
  sentiment_scored: number
}

export function News() {
  const qc = useQueryClient()
  const [symbol, setSymbol] = useState('')
  const [event, setEvent] = useState('')
  const [hideRoutine, setHideRoutine] = useState(true)
  const params = new URLSearchParams({ limit: '300', ...(symbol ? { symbol } : {}), ...(event ? { event } : {}) })
  const news = useQuery({ queryKey: ['news', symbol, event], queryFn: () => apiGet<NewsRow[]>(`/news?${params}`) })
  const ingest = useMutation({
    mutationFn: (source: string) => apiPost<IngestStats>(`/news/ingest/${source}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['news'] }),
  })
  const rows = (news.data ?? []).filter((n) => !hideRoutine || !['routine_disclosure', 'investor_meet'].includes(n.event_type))
  const events = [...new Set((news.data ?? []).map((n) => n.event_type))].sort()

  return (
    <>
      <PageHeader title="News Intelligence">
        {SOURCES.map(([s, label]) => (
          <Button key={s} onClick={() => ingest.mutate(s)} disabled={ingest.isPending} title={`Fetch ${label} now`}>
            {ingest.isPending && ingest.variables === s ? 'Fetching…' : `Fetch ${label}`}
          </Button>
        ))}
      </PageHeader>
      <div className="flex flex-col gap-3 p-3">
        {ingest.data && (
          <div role="status" className="num border border-up/40 bg-up/10 px-3 py-1.5 text-[12px] text-up">
            {ingest.data.received} received · {ingest.data.inserted} new · {ingest.data.duplicates} duplicates ·{' '}
            {ingest.data.near_duplicates} near-duplicates · {ingest.data.mapped_to_instrument} mapped to stocks ·{' '}
            {ingest.data.sentiment_scored} scored by FinBERT
          </div>
        )}
        {ingest.error && <div role="alert" className="border border-down/40 bg-down/10 px-3 py-1.5 text-down">{ingest.error.message}</div>}
        <Note>
          Official public feeds only. The first fetch loads FinBERT (~20–30 s). Each item is usable by the decision engine only from
          max(published, ingested) time, so nothing from the future can influence a decision. Historical announcements are a paid
          NSE product, so models are trained on market data and news is used live.
        </Note>
        <Panel title={`Items (${rows.length})`} right={
          <div className="flex items-center gap-2">
            <input aria-label="Filter by symbol" placeholder="Symbol" value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              className="h-6 w-28 border border-line bg-bg px-2 text-[11px] text-fg placeholder:text-dim" />
            <select aria-label="Filter by event" value={event} onChange={(e) => setEvent(e.target.value)}
              className="h-6 border border-line bg-bg px-1 text-[11px] text-fg">
              <option value="">All events</option>
              {events.map((e) => <option key={e} value={e}>{e.replaceAll('_', ' ')}</option>)}
            </select>
            <label className="flex items-center gap-1 text-[11px] text-muted">
              <input type="checkbox" checked={hideRoutine} onChange={(e) => setHideRoutine(e.target.checked)} /> hide routine
            </label>
          </div>
        }>
          <QueryState isPending={news.isPending} error={news.error} isEmpty={!rows.length}
            empty="No items. Use the Fetch buttons above to ingest the official feeds.">
            <div className="max-h-[calc(100vh-260px)] overflow-auto">
              <Table dense head={['Usable from', 'Source', 'Symbols', 'Event', 'Importance', 'Sentiment', 'Score', 'Headline']}>
                {rows.map((n) => (
                  <tr key={n.id}>
                    <td className="text-dim">{dateTime(n.usable_from)}</td>
                    <td className="text-muted">{n.source.replace('_', ' ')}</td>
                    <td className="font-medium">{n.symbols.join(', ') || '—'}</td>
                    <td className="text-muted">{n.event_type.replaceAll('_', ' ')}</td>
                    <td className="num">{pct(n.importance, 0)}</td>
                    <td>{n.sentiment && <Badge tone={n.sentiment === 'positive' ? 'up' : n.sentiment === 'negative' ? 'down' : 'muted'}>{n.sentiment}</Badge>}</td>
                    <td className={`num ${tone(n.sentiment_score)}`}>{signed(n.sentiment_score, 2)}</td>
                    <td className="max-w-[560px] truncate">
                      <a href={n.url} target="_blank" rel="noreferrer noopener" className="hover:text-info" title={n.title}>{n.title}</a>
                    </td>
                  </tr>
                ))}
              </Table>
            </div>
          </QueryState>
        </Panel>
      </div>
    </>
  )
}
