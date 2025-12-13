'use client'
import { useState, useEffect, useCallback } from 'react'
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts'

// Types
interface Position { symbol: string; side: string; size: number; entry_price: number; current_price: number; pnl_pct: number; leverage: number }
interface BotSnapshot { timestamp_utc: string; execution: { mode: string; trading_mode: string; is_paused: boolean }; account: { equity: number; free_margin: number; day_pnl_pct: number }; positions: { count: number; list: Position[]; total_pnl_usd: number }; ai_budget: { claude_calls_today: number; claude_limit_per_day: number; openai_calls_today: number; openai_limit_per_day: number }; global_ia: { enabled: boolean; last_call_minutes_ago?: number } }
interface PnLSummary { current_equity: number; pnl_all_time_pct: number; pnl_all_time_usd: number; pnl_day_pct: number; pnl_day_usd: number; pnl_week_pct: number; pnl_week_usd: number; pnl_month_pct: number; pnl_month_usd: number; winrate: number; profit_factor: number; max_drawdown_pct: number; total_trades: number }
interface EquityPoint { ts: string; equity_usd: number }
interface Fill { id: number; ts: string; symbol: string; side: string; qty: number; price: number; realized_pnl: number }

// Components
const Card = ({ title, children, className = '' }: { title?: string; children: React.ReactNode; className?: string }) => (
  <div className={`bg-dark-700 rounded-xl border border-dark-500 p-4 ${className}`}>
    {title && <div className="text-sm font-medium text-neutral mb-3">{title}</div>}
    {children}
  </div>
)

const PnLCard = ({ title, pct, usd, highlight = false }: { title: string; pct: number; usd: number; highlight?: boolean }) => {
  const pos = pct >= 0
  return (
    <div className={`bg-dark-700 rounded-xl border p-4 ${highlight ? (pos ? 'border-profit/30 bg-profit/5' : 'border-loss/30 bg-loss/5') : 'border-dark-500'}`}>
      <div className="text-xs text-neutral mb-1">{title}</div>
      <div className={`text-2xl font-bold ${pos ? 'text-profit' : 'text-loss'}`}>{pos ? '+' : ''}{pct.toFixed(2)}%</div>
      <div className={`text-sm ${pos ? 'text-profit' : 'text-loss'}`}>{pos ? '+' : ''}${usd.toFixed(2)}</div>
    </div>
  )
}

const EquityChart = ({ data, range, onRangeChange }: { data: EquityPoint[]; range: string; onRangeChange: (r: string) => void }) => {
  if (!data?.length) return <Card title="📈 Equity Curve"><div className="h-64 flex items-center justify-center text-neutral">Aguardando dados...</div></Card>
  const chartData = data.map(p => ({ time: new Date(p.ts).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }), equity: p.equity_usd }))
  const vals = data.map(d => d.equity_usd)
  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-medium">📈 Equity Curve (ALL TIME)</span>
        <div className="flex gap-1">{['1d', '7d', '30d', 'all'].map(r => <button key={r} onClick={() => onRangeChange(r)} className={`px-2 py-1 rounded text-xs ${range === r ? 'bg-blue-500 text-white' : 'bg-dark-600 text-neutral'}`}>{r.toUpperCase()}</button>)}</div>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs><linearGradient id="colorEq" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4}/><stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/></linearGradient></defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis dataKey="time" stroke="#666" tick={{ fill: '#888', fontSize: 10 }} interval="preserveStartEnd"/>
            <YAxis stroke="#666" tick={{ fill: '#888', fontSize: 10 }} domain={[Math.min(...vals) * 0.995, Math.max(...vals) * 1.005]} tickFormatter={v => `$${v.toFixed(0)}`}/>
            <Tooltip contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333', borderRadius: '8px' }} formatter={(v: number) => [`$${v.toFixed(2)}`, 'Equity']}/>
            <Area type="monotone" dataKey="equity" stroke="#3b82f6" fill="url(#colorEq)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

const TradesTable = ({ fills, range, onRangeChange }: { fills: Fill[]; range: string; onRangeChange: (r: string) => void }) => (
  <Card>
    <div className="flex items-center justify-between mb-4">
      <span className="text-sm font-medium">📋 Histórico de Trades ({fills.length})</span>
      <div className="flex gap-1">{['7d', '30d', 'all'].map(r => <button key={r} onClick={() => onRangeChange(r)} className={`px-2 py-1 rounded text-xs ${range === r ? 'bg-blue-500 text-white' : 'bg-dark-600 text-neutral'}`}>{r.toUpperCase()}</button>)}</div>
    </div>
    {!fills.length ? <div className="text-neutral text-center py-8">Nenhum trade</div> : (
      <div className="overflow-x-auto max-h-72">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-dark-700"><tr className="text-neutral border-b border-dark-500"><th className="text-left py-2 px-2">Data</th><th className="text-left py-2 px-2">Symbol</th><th className="text-left py-2 px-2">Side</th><th className="text-right py-2 px-2">Qty</th><th className="text-right py-2 px-2">Price</th><th className="text-right py-2 px-2">PnL</th></tr></thead>
          <tbody>{fills.map((f, i) => <tr key={f.id || i} className="border-b border-dark-600 hover:bg-dark-600"><td className="py-2 px-2 text-neutral">{new Date(f.ts).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</td><td className="py-2 px-2 font-medium">{f.symbol}</td><td className={`py-2 px-2 ${f.side === 'buy' || f.side === 'long' ? 'text-profit' : 'text-loss'}`}>{f.side?.toUpperCase()}</td><td className="py-2 px-2 text-right">{f.qty}</td><td className="py-2 px-2 text-right">${f.price?.toFixed(2)}</td><td className={`py-2 px-2 text-right font-medium ${f.realized_pnl >= 0 ? 'text-profit' : 'text-loss'}`}>{f.realized_pnl >= 0 ? '+' : ''}${f.realized_pnl?.toFixed(2)}</td></tr>)}</tbody>
        </table>
      </div>
    )}
  </Card>
)

const PositionsTable = ({ positions }: { positions: Position[] }) => (
  <Card title={`📊 Posições (${positions?.length || 0})`}>
    {!positions?.length ? <div className="text-neutral text-center py-4">Nenhuma posição</div> : (
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr className="text-neutral border-b border-dark-500"><th className="text-left py-2 px-2">Symbol</th><th className="text-left py-2 px-2">Side</th><th className="text-right py-2 px-2">Size</th><th className="text-right py-2 px-2">Entry</th><th className="text-right py-2 px-2">Price</th><th className="text-right py-2 px-2">PnL</th></tr></thead>
          <tbody>{positions.map((p, i) => <tr key={i} className="border-b border-dark-600"><td className="py-2 px-2 font-medium">{p.symbol}</td><td className={`py-2 px-2 ${p.side === 'long' ? 'text-profit' : 'text-loss'}`}>{p.side?.toUpperCase()}</td><td className="py-2 px-2 text-right">{p.size}</td><td className="py-2 px-2 text-right">${p.entry_price?.toFixed(2)}</td><td className="py-2 px-2 text-right">${p.current_price?.toFixed(2)}</td><td className={`py-2 px-2 text-right font-medium ${p.pnl_pct >= 0 ? 'text-profit' : 'text-loss'}`}>{p.pnl_pct >= 0 ? '+' : ''}{p.pnl_pct?.toFixed(2)}%</td></tr>)}</tbody>
        </table>
      </div>
    )}
  </Card>
)

const MetricsPanel = ({ pnl }: { pnl: PnLSummary | null }) => {
  if (!pnl) return <Card title="📊 Métricas"><div className="text-neutral text-center py-4">Carregando...</div></Card>
  return (
    <Card title="📊 Performance">
      <div className="grid grid-cols-2 gap-3">
        <div><div className="text-xs text-neutral">Win Rate</div><div className={`text-lg font-semibold ${pnl.winrate >= 50 ? 'text-profit' : 'text-loss'}`}>{pnl.winrate?.toFixed(1) || 0}%</div></div>
        <div><div className="text-xs text-neutral">Profit Factor</div><div className={`text-lg font-semibold ${pnl.profit_factor >= 1 ? 'text-profit' : 'text-loss'}`}>{pnl.profit_factor?.toFixed(2) || 0}</div></div>
        <div><div className="text-xs text-neutral">Max Drawdown</div><div className="text-lg font-semibold text-loss">-{pnl.max_drawdown_pct?.toFixed(1) || 0}%</div></div>
        <div><div className="text-xs text-neutral">Total Trades</div><div className="text-lg font-semibold">{pnl.total_trades || 0}</div></div>
      </div>
    </Card>
  )
}

const AIPanel = ({ globalIa, aiBudget }: { globalIa: BotSnapshot['global_ia']; aiBudget: BotSnapshot['ai_budget'] }) => (
  <Card title="🧠 GLOBAL_IA">
    <div className="space-y-3">
      <div className="flex items-center justify-between"><span className="text-neutral text-xs">Status</span><span className={`px-2 py-0.5 rounded-full text-xs ${globalIa.enabled ? 'bg-profit/20 text-profit' : 'bg-neutral/20 text-neutral'}`}>{globalIa.enabled ? '✅ ON' : '❌ OFF'}</span></div>
      {globalIa.last_call_minutes_ago !== undefined && <div className="flex items-center justify-between"><span className="text-neutral text-xs">Last</span><span className="text-xs">{globalIa.last_call_minutes_ago?.toFixed(0)}min</span></div>}
      <div className="pt-2 border-t border-dark-500 grid grid-cols-2 gap-2">
        <div><div className="text-xs text-neutral">Claude</div><div className="text-sm">{aiBudget?.claude_calls_today || 0}/{aiBudget?.claude_limit_per_day || 12}</div><div className="w-full bg-dark-500 rounded-full h-1.5 mt-1"><div className="bg-purple-500 h-1.5 rounded-full" style={{ width: `${Math.min(100, ((aiBudget?.claude_calls_today || 0) / (aiBudget?.claude_limit_per_day || 12)) * 100)}%` }} /></div></div>
        <div><div className="text-xs text-neutral">OpenAI</div><div className="text-sm">{aiBudget?.openai_calls_today || 0}/{aiBudget?.openai_limit_per_day || 40}</div><div className="w-full bg-dark-500 rounded-full h-1.5 mt-1"><div className="bg-cyan-500 h-1.5 rounded-full" style={{ width: `${Math.min(100, ((aiBudget?.openai_calls_today || 0) / (aiBudget?.openai_limit_per_day || 40)) * 100)}%` }} /></div></div>
      </div>
    </div>
  </Card>
)

const Badge = ({ mode, paused }: { mode: string; paused: boolean }) => {
  if (paused) return <span className="px-2 py-1 rounded-full bg-yellow-500/20 text-yellow-500 text-xs">⏸️ PAUSED</span>
  const m = mode?.toUpperCase() || 'UNKNOWN'
  const c: Record<string, string> = { 'LIVE': 'bg-red-500/20 text-red-400', 'PAPER_ONLY': 'bg-blue-500/20 text-blue-400', 'PAPER': 'bg-blue-500/20 text-blue-400', 'SHADOW': 'bg-purple-500/20 text-purple-400' }
  const i: Record<string, string> = { 'LIVE': '🔴', 'PAPER_ONLY': '🟢', 'PAPER': '🟢', 'SHADOW': '🟣' }
  return <span className={`px-2 py-1 rounded-full text-xs ${c[m] || 'bg-neutral/20 text-neutral'}`}>{i[m] || '⚪'} {m === 'PAPER_ONLY' ? 'PAPER' : m}</span>
}

// Main Dashboard
export function Dashboard() {
  const [snapshot, setSnapshot] = useState<BotSnapshot | null>(null)
  const [pnlSummary, setPnlSummary] = useState<PnLSummary | null>(null)
  const [equitySeries, setEquitySeries] = useState<EquityPoint[]>([])
  const [fills, setFills] = useState<Fill[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const [chartRange, setChartRange] = useState('7d')
  const [tradesRange, setTradesRange] = useState('7d')
  const [stale, setStale] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      const [snapRes, pnlRes] = await Promise.all([
        fetch('/api/bot-snapshot', { cache: 'no-store' }),
        fetch('/api/bot-pnl-summary', { cache: 'no-store' })
      ])
      if (snapRes.ok) { const d = await snapRes.json(); if (!d.error) { setSnapshot(d); setError(null); setLastUpdate(new Date()); setStale(false) } }
      if (pnlRes.ok) { const d = await pnlRes.json(); if (!d.error) setPnlSummary(d) }
    } catch (e) { console.error(e); setStale(true); if (!snapshot) setError(e instanceof Error ? e.message : 'Erro') }
    finally { setLoading(false) }
  }, [snapshot])

  const fetchSeries = useCallback(async () => {
    try {
      const res = await fetch(`/api/bot-pnl-series?range=${chartRange}`, { cache: 'no-store' })
      if (res.ok) { const d = await res.json(); setEquitySeries(d.data || []) }
    } catch (e) { console.error(e) }
  }, [chartRange])

  const fetchFills = useCallback(async () => {
    try {
      const res = await fetch(`/api/bot-fills?range=${tradesRange}`, { cache: 'no-store' })
      if (res.ok) { const d = await res.json(); setFills(d.fills || []) }
    } catch (e) { console.error(e) }
  }, [tradesRange])

  useEffect(() => { fetchData(); fetchSeries(); fetchFills(); const i = setInterval(() => { fetchData(); fetchSeries() }, 15000); return () => clearInterval(i) }, [])
  useEffect(() => { fetchSeries() }, [chartRange])
  useEffect(() => { fetchFills() }, [tradesRange])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div></div>
  if (error && !snapshot) return <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-6 text-center"><div className="text-red-500 text-lg mb-2">❌ Erro</div><div className="text-neutral">{error}</div></div>

  const s = snapshot!
  return (
    <div className="min-h-screen bg-dark-900 p-4">
      {/* Header */}
      <header className="flex items-center justify-between mb-6">
        <div><h1 className="text-xl font-bold">🤖 InspetorPro Dashboard</h1><p className="text-neutral text-xs">Premium Trading Analytics</p></div>
        <div className="flex items-center gap-3">
          <Badge mode={s.execution.mode} paused={s.execution.is_paused} />
          {stale && <span className="text-yellow-500 text-xs">⚠️ Stale</span>}
          {lastUpdate && <span className="text-xs text-neutral">{lastUpdate.toLocaleTimeString('pt-BR')}</span>}
        </div>
      </header>

      {/* PnL Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <PnLCard title="🏆 ALL TIME" pct={pnlSummary?.pnl_all_time_pct || 0} usd={pnlSummary?.pnl_all_time_usd || 0} highlight />
        <PnLCard title="📅 Hoje" pct={pnlSummary?.pnl_day_pct || s.account.day_pnl_pct || 0} usd={pnlSummary?.pnl_day_usd || 0} />
        <PnLCard title="📆 Semana" pct={pnlSummary?.pnl_week_pct || 0} usd={pnlSummary?.pnl_week_usd || 0} />
        <PnLCard title="🗓️ Mês" pct={pnlSummary?.pnl_month_pct || 0} usd={pnlSummary?.pnl_month_usd || 0} />
      </div>

      {/* Equity & Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-6">
        <div className="lg:col-span-3"><EquityChart data={equitySeries} range={chartRange} onRangeChange={setChartRange} /></div>
        <div><MetricsPanel pnl={pnlSummary} /></div>
      </div>

      {/* Trades & Positions & AI */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2"><TradesTable fills={fills} range={tradesRange} onRangeChange={setTradesRange} /></div>
        <div className="space-y-4">
          <PositionsTable positions={s.positions.list} />
          <AIPanel globalIa={s.global_ia} aiBudget={s.ai_budget} />
        </div>
      </div>

      {/* Footer */}
      <footer className="mt-6 text-center text-neutral text-xs">
        <p>AI Mode: {s.execution.trading_mode} | Exec: {s.execution.mode} | Equity: ${s.account.equity?.toFixed(2)}</p>
      </footer>
    </div>
  )
}
