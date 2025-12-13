'use client'
import { useState, useEffect, useCallback } from 'react'
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, ReferenceDot } from 'recharts'

// Types
interface Position { symbol: string; side: string; size: number; entry_price: number; current_price: number; pnl_pct: number; leverage: number; liquidation_px?: number; margin_used?: number; unrealized_pnl?: number }
interface AccountInfo { equity: number; account_value: number; free_margin: number; withdrawable: number; used_margin: number; position_value: number; unrealized_pnl: number; leverage: number; long_exposure: number; short_exposure: number; roe_pct: number; direction_bias: string; margin_usage_pct: number; day_pnl_pct: number }
interface BotSnapshot { timestamp_utc: string; execution: { mode: string; trading_mode: string; is_paused: boolean }; account: AccountInfo; positions: { count: number; list: Position[]; total_pnl_usd: number }; ai_budget: { claude_calls_today: number; claude_limit_per_day: number; openai_calls_today: number; openai_limit_per_day: number }; global_ia: { enabled: boolean; last_call_minutes_ago?: number } }
interface PnLSummary { current_equity: number; pnl_all_time_pct: number; pnl_all_time_usd: number; pnl_day_pct: number; pnl_day_usd: number; pnl_week_pct: number; pnl_week_usd: number; pnl_month_pct: number; pnl_month_usd: number; winrate: number; profit_factor: number; max_drawdown_pct: number; total_trades: number; trades_today: number }
interface EquityPoint { ts: string; equity_usd: number }
interface Fill { id: number; ts: string; symbol: string; side: string; qty: number; price: number; realized_pnl: number; fee: number; is_close: boolean }

// Card Components
const Card = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <div className={`bg-[#1a1a1a] rounded-lg border border-[#2a2a2a] p-4 ${className}`}>{children}</div>
)

const MetricCard = ({ label, value, suffix = '', color = 'white', small = false }: { label: string; value: string | number; suffix?: string; color?: string; small?: boolean }) => (
  <div className={small ? 'text-center' : ''}>
    <div className="text-[10px] text-gray-500 uppercase tracking-wide">{label}</div>
    <div className={`font-semibold ${small ? 'text-sm' : 'text-lg'} ${color === 'green' ? 'text-[#00ff88]' : color === 'red' ? 'text-[#ff4d4d]' : 'text-white'}`}>
      {typeof value === 'number' ? value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : value}{suffix}
    </div>
  </div>
)

// Top Stats Bar (HyperDash style)
const TopStats = ({ account }: { account: AccountInfo }) => (
  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-4">
    <Card><MetricCard label="Total Value" value={account.account_value} suffix="" /></Card>
    <Card><MetricCard label="Withdrawable" value={account.withdrawable} suffix="" color={account.withdrawable > 0 ? 'green' : 'white'} /></Card>
    <Card><MetricCard label="Leverage" value={account.leverage.toFixed(2)} suffix="x" /></Card>
    <Card><MetricCard label="Position Value" value={account.position_value} suffix="" /></Card>
    <Card><MetricCard label="Unrealized PnL" value={account.unrealized_pnl} suffix="" color={account.unrealized_pnl >= 0 ? 'green' : 'red'} /></Card>
    <Card><MetricCard label="ROE" value={account.roe_pct.toFixed(2)} suffix="%" color={account.roe_pct >= 0 ? 'green' : 'red'} /></Card>
    <Card>
      <div className="text-[10px] text-gray-500 uppercase">Direction Bias</div>
      <div className={`font-semibold ${account.direction_bias === 'LONG' ? 'text-[#00ff88]' : account.direction_bias === 'SHORT' ? 'text-[#ff4d4d]' : 'text-gray-400'}`}>
        {account.direction_bias === 'LONG' ? '↗ LONG' : account.direction_bias === 'SHORT' ? '↘ SHORT' : '→ NEUTRAL'}
      </div>
      <div className="flex gap-1 mt-1">
        <div className="h-1.5 rounded-full bg-[#00ff88]" style={{ width: `${account.long_exposure}%` }} />
        <div className="h-1.5 rounded-full bg-[#ff4d4d]" style={{ width: `${account.short_exposure}%` }} />
      </div>
    </Card>
  </div>
)

// PnL Cards Row
const PnLCards = ({ pnl, dayPnl }: { pnl: PnLSummary | null; dayPnl: number }) => {
  const cards = [
    { label: '🏆 ALL TIME', pct: pnl?.pnl_all_time_pct || 0, usd: pnl?.pnl_all_time_usd || 0, highlight: true },
    { label: '📅 24H', pct: pnl?.pnl_day_pct || dayPnl, usd: pnl?.pnl_day_usd || 0 },
    { label: '📆 7D', pct: pnl?.pnl_week_pct || 0, usd: pnl?.pnl_week_usd || 0 },
    { label: '🗓️ 30D', pct: pnl?.pnl_month_pct || 0, usd: pnl?.pnl_month_usd || 0 },
  ]
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
      {cards.map((c, i) => {
        const pos = c.pct >= 0
        return (
          <Card key={i} className={c.highlight ? (pos ? 'border-[#00ff88]/30 bg-[#00ff88]/5' : 'border-[#ff4d4d]/30 bg-[#ff4d4d]/5') : ''}>
            <div className="text-xs text-gray-500">{c.label}</div>
            <div className={`text-2xl font-bold ${pos ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{pos ? '+' : ''}{c.pct.toFixed(2)}%</div>
            <div className={`text-sm ${pos ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{pos ? '+' : ''}${c.usd.toFixed(2)}</div>
          </Card>
        )
      })}
    </div>
  )
}

// Equity Chart (HyperDash style with gradient)
const EquityChart = ({ data, range, onRangeChange, metric, onMetricChange }: { data: EquityPoint[]; range: string; onRangeChange: (r: string) => void; metric: string; onMetricChange: (m: string) => void }) => {
  if (!data?.length) return <Card className="h-80"><div className="h-full flex items-center justify-center text-gray-500">Carregando gráfico...</div></Card>
  
  const chartData = data.map(p => ({ time: new Date(p.ts).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }), value: p.equity_usd, ts: p.ts }))
  const vals = data.map(d => d.equity_usd)
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const first = vals[0] || 0
  const last = vals[vals.length - 1] || 0
  const pnl = last - first
  const isPositive = pnl >= 0
  const color = isPositive ? '#00ff88' : '#ff4d4d'

  return (
    <Card className="h-80">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-4">
          <span className="text-sm font-medium">Perp Equity</span>
          <span className="text-xl font-bold">${last.toFixed(2)}</span>
          <div className="text-xs text-gray-500">Margin Usage <span className="text-white">{((last > 0 ? (last - min) / last : 0) * 100).toFixed(1)}%</span></div>
        </div>
        <div className="flex gap-1">
          {['24H', '1W', '1M', 'All'].map(r => <button key={r} onClick={() => onRangeChange(r === '24H' ? '1d' : r === '1W' ? '7d' : r === '1M' ? '30d' : 'all')} className={`px-2 py-1 rounded text-xs ${(range === '1d' && r === '24H') || (range === '7d' && r === '1W') || (range === '30d' && r === '1M') || (range === 'all' && r === 'All') ? 'bg-[#00b8ff] text-white' : 'bg-[#2a2a2a] text-gray-400 hover:bg-[#3a3a3a]'}`}>{r}</button>)}
        </div>
      </div>
      <div className="flex gap-2 mb-2">
        {['Combined', 'Perp Only', 'PnL', 'Account Value'].map(m => <button key={m} onClick={() => onMetricChange(m)} className={`px-2 py-0.5 rounded text-xs ${metric === m ? 'bg-[#00b8ff]/20 text-[#00b8ff] border border-[#00b8ff]' : 'text-gray-500 hover:text-gray-300'}`}>{m}</button>)}
      </div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="colorVal" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.3}/>
                <stop offset="95%" stopColor={color} stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
            <XAxis dataKey="time" stroke="#666" tick={{ fill: '#666', fontSize: 9 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
            <YAxis stroke="#666" tick={{ fill: '#666', fontSize: 9 }} tickLine={false} axisLine={false} domain={[min * 0.998, max * 1.002]} tickFormatter={v => `$${v.toFixed(0)}`} width={50} />
            <Tooltip contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333', borderRadius: '8px', fontSize: '12px' }} formatter={(v: number) => [`$${v.toFixed(2)}`, 'Equity']} labelStyle={{ color: '#888' }} />
            <Area type="monotone" dataKey="value" stroke={color} fill="url(#colorVal)" strokeWidth={2} dot={false} />
            <ReferenceDot x={chartData[chartData.length - 1]?.time} y={last} r={4} fill={color} stroke="#1a1a1a" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="text-right text-sm mt-1">
        <span className="text-gray-500">{range.toUpperCase()} PnL (Combined)</span>
        <span className={`ml-2 font-semibold ${isPositive ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>${pnl.toFixed(2)}</span>
      </div>
    </Card>
  )
}

// Left Sidebar Metrics
const LeftMetrics = ({ account, pnl }: { account: AccountInfo; pnl: PnLSummary | null }) => (
  <Card className="space-y-4">
    <div>
      <div className="text-xs text-gray-500">Direction Bias</div>
      <div className={`text-lg font-semibold ${account.direction_bias === 'LONG' ? 'text-[#00ff88]' : account.direction_bias === 'SHORT' ? 'text-[#ff4d4d]' : 'text-gray-400'}`}>
        {account.direction_bias === 'LONG' ? '↗ LONG' : account.direction_bias === 'SHORT' ? '↘ SHORT' : '→ NEUTRAL'}
      </div>
      <div className="text-xs text-gray-500 mt-1">Long Exposure <span className="text-[#00ff88]">{account.long_exposure.toFixed(0)}%</span></div>
      <div className="w-full h-2 bg-[#2a2a2a] rounded-full mt-1 overflow-hidden flex">
        <div className="h-full bg-[#00ff88]" style={{ width: `${account.long_exposure}%` }} />
        <div className="h-full bg-[#ff4d4d]" style={{ width: `${account.short_exposure}%` }} />
      </div>
    </div>
    <div className="border-t border-[#2a2a2a] pt-3">
      <div className="text-xs text-gray-500">Unrealized PnL</div>
      <div className={`text-lg font-semibold ${account.unrealized_pnl >= 0 ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>${account.unrealized_pnl.toFixed(2)}</div>
      <div className={`text-xs ${account.roe_pct >= 0 ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>↑ {account.roe_pct.toFixed(2)}% ROE</div>
    </div>
    <div className="border-t border-[#2a2a2a] pt-3">
      <div className="text-xs text-gray-500 mb-2">Performance</div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div><span className="text-gray-500">Win Rate</span><div className={`font-medium ${(pnl?.winrate || 0) >= 50 ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{pnl?.winrate?.toFixed(1) || 0}%</div></div>
        <div><span className="text-gray-500">Profit Factor</span><div className={`font-medium ${(pnl?.profit_factor || 0) >= 1 ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{pnl?.profit_factor?.toFixed(2) || 0}</div></div>
        <div><span className="text-gray-500">Max Drawdown</span><div className="font-medium text-[#ff4d4d]">-{pnl?.max_drawdown_pct?.toFixed(1) || 0}%</div></div>
        <div><span className="text-gray-500">Total Trades</span><div className="font-medium text-white">{pnl?.total_trades || 0}</div></div>
      </div>
    </div>
  </Card>
)

// Positions Table (HyperDash style)
const PositionsTable = ({ positions }: { positions: Position[] }) => (
  <Card>
    <div className="flex items-center justify-between mb-3">
      <div className="text-sm font-medium">Positions <span className="text-gray-500">({positions.length})</span></div>
      <div className="text-xs text-gray-500">
        Total <span className="text-white">${positions.reduce((a, p) => a + (p.size * p.entry_price), 0).toFixed(2)}</span>
        {' • '}Long <span className="text-[#00ff88]">${positions.filter(p => p.side === 'long').reduce((a, p) => a + (p.size * p.entry_price), 0).toFixed(2)}</span>
        {' • '}Short <span className="text-[#ff4d4d]">${positions.filter(p => p.side === 'short').reduce((a, p) => a + Math.abs(p.size * p.entry_price), 0).toFixed(2)}</span>
      </div>
    </div>
    {!positions.length ? <div className="text-gray-500 text-center py-4 text-sm">Nenhuma posição aberta</div> : (
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr className="text-gray-500 border-b border-[#2a2a2a]">
            <th className="text-left py-2 font-normal">Asset</th>
            <th className="text-left py-2 font-normal">Type</th>
            <th className="text-right py-2 font-normal">Size</th>
            <th className="text-right py-2 font-normal">Entry</th>
            <th className="text-right py-2 font-normal">Current</th>
            <th className="text-right py-2 font-normal">Liq. Price</th>
            <th className="text-right py-2 font-normal">PnL</th>
          </tr></thead>
          <tbody>
            {positions.map((p, i) => (
              <tr key={i} className="border-b border-[#2a2a2a]/50 hover:bg-[#2a2a2a]/30">
                <td className="py-2 font-medium">{p.symbol}</td>
                <td className={`py-2 ${p.side === 'long' ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{p.side?.toUpperCase()}</td>
                <td className="py-2 text-right">{p.size} <span className="text-gray-500">({p.leverage}x)</span></td>
                <td className="py-2 text-right">${p.entry_price?.toFixed(2)}</td>
                <td className="py-2 text-right">${p.current_price?.toFixed(2)}</td>
                <td className="py-2 text-right text-gray-500">{p.liquidation_px ? `$${p.liquidation_px.toFixed(2)}` : '—'}</td>
                <td className={`py-2 text-right font-medium ${p.pnl_pct >= 0 ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{p.pnl_pct >= 0 ? '+' : ''}{p.pnl_pct?.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </Card>
)

// Trades/Fills Table
const TradesTable = ({ fills, range, onRangeChange }: { fills: Fill[]; range: string; onRangeChange: (r: string) => void }) => {
  const [tab, setTab] = useState<'recent' | 'completed'>('recent')
  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <div className="flex gap-2">
          {['recent', 'completed'].map(t => <button key={t} onClick={() => setTab(t as 'recent' | 'completed')} className={`px-3 py-1 rounded text-xs ${tab === t ? 'bg-[#00b8ff]/20 text-[#00b8ff]' : 'text-gray-500 hover:text-gray-300'}`}>{t === 'recent' ? 'Recent Fills' : 'Completed Trades'}</button>)}
        </div>
        <div className="flex gap-1">
          {['7d', '30d', 'all'].map(r => <button key={r} onClick={() => onRangeChange(r)} className={`px-2 py-1 rounded text-xs ${range === r ? 'bg-[#00b8ff] text-white' : 'bg-[#2a2a2a] text-gray-400'}`}>{r.toUpperCase()}</button>)}
        </div>
      </div>
      {!fills.length ? <div className="text-gray-500 text-center py-8 text-sm">Nenhum trade registrado</div> : (
        <div className="overflow-x-auto max-h-64">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-[#1a1a1a]"><tr className="text-gray-500 border-b border-[#2a2a2a]">
              <th className="text-left py-2 font-normal">Time</th>
              <th className="text-left py-2 font-normal">Asset</th>
              <th className="text-left py-2 font-normal">Side</th>
              <th className="text-right py-2 font-normal">Size</th>
              <th className="text-right py-2 font-normal">Price</th>
              <th className="text-right py-2 font-normal">Fee</th>
              <th className="text-right py-2 font-normal">PnL</th>
            </tr></thead>
            <tbody>
              {fills.map((f, i) => (
                <tr key={f.id || i} className="border-b border-[#2a2a2a]/50 hover:bg-[#2a2a2a]/30">
                  <td className="py-2 text-gray-500">{new Date(f.ts).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</td>
                  <td className="py-2 font-medium">{f.symbol}</td>
                  <td className={`py-2 ${f.side === 'buy' || f.side === 'long' || f.side === 'B' ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{f.side?.toUpperCase()}</td>
                  <td className="py-2 text-right">{f.qty}</td>
                  <td className="py-2 text-right">${f.price?.toFixed(2)}</td>
                  <td className="py-2 text-right text-gray-500">${f.fee?.toFixed(4)}</td>
                  <td className={`py-2 text-right font-medium ${f.realized_pnl >= 0 ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{f.realized_pnl !== 0 ? `${f.realized_pnl >= 0 ? '+' : ''}$${f.realized_pnl.toFixed(2)}` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

// Badge
const Badge = ({ mode, paused }: { mode: string; paused: boolean }) => {
  if (paused) return <span className="px-2 py-1 rounded text-xs bg-yellow-500/20 text-yellow-400">⏸️ PAUSED</span>
  const m = mode?.toUpperCase() || ''
  if (m.includes('LIVE')) return <span className="px-2 py-1 rounded text-xs bg-[#ff4d4d]/20 text-[#ff4d4d]">🔴 LIVE</span>
  if (m.includes('SHADOW')) return <span className="px-2 py-1 rounded text-xs bg-purple-500/20 text-purple-400">🟣 SHADOW</span>
  return <span className="px-2 py-1 rounded text-xs bg-[#00b8ff]/20 text-[#00b8ff]">🟢 PAPER</span>
}

// Main Dashboard
export function Dashboard() {
  const [snapshot, setSnapshot] = useState<BotSnapshot | null>(null)
  const [pnlSummary, setPnlSummary] = useState<PnLSummary | null>(null)
  const [equitySeries, setEquitySeries] = useState<EquityPoint[]>([])
  const [fills, setFills] = useState<Fill[]>([])
  const [loading, setLoading] = useState(true)
  const [chartRange, setChartRange] = useState('7d')
  const [chartMetric, setChartMetric] = useState('Combined')
  const [tradesRange, setTradesRange] = useState('7d')
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  const fetchAll = useCallback(async () => {
    try {
      const [snapRes, pnlRes, seriesRes, fillsRes] = await Promise.all([
        fetch('/api/bot-snapshot', { cache: 'no-store' }),
        fetch('/api/bot-pnl-summary', { cache: 'no-store' }),
        fetch(`/api/bot-pnl-series?range=${chartRange}`, { cache: 'no-store' }),
        fetch(`/api/bot-fills?range=${tradesRange}`, { cache: 'no-store' })
      ])
      if (snapRes.ok) { const d = await snapRes.json(); if (!d.error) setSnapshot(d) }
      if (pnlRes.ok) { const d = await pnlRes.json(); if (!d.error) setPnlSummary(d) }
      if (seriesRes.ok) { const d = await seriesRes.json(); setEquitySeries(d.data || []) }
      if (fillsRes.ok) { const d = await fillsRes.json(); setFills(d.fills || []) }
      setLastUpdate(new Date())
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }, [chartRange, tradesRange])

  useEffect(() => { fetchAll(); const i = setInterval(fetchAll, 10000); return () => clearInterval(i) }, [fetchAll])

  if (loading) return <div className="min-h-screen bg-[#0d0d0d] flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-t-2 border-[#00b8ff]" /></div>
  if (!snapshot) return <div className="min-h-screen bg-[#0d0d0d] flex items-center justify-center text-gray-500">Conectando ao bot...</div>

  return (
    <div className="min-h-screen bg-[#0d0d0d] text-white p-4">
      {/* Header */}
      <header className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-bold">🤖 InspetorPro Dashboard</h1>
          <Badge mode={snapshot.execution.mode} paused={snapshot.execution.is_paused} />
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span>AI: {snapshot.execution.trading_mode}</span>
          <span>Next refresh in {lastUpdate ? Math.max(0, 10 - Math.floor((Date.now() - lastUpdate.getTime()) / 1000)) : 10}s</span>
        </div>
      </header>

      {/* Top Stats */}
      <TopStats account={snapshot.account} />

      {/* PnL Cards */}
      <PnLCards pnl={pnlSummary} dayPnl={snapshot.account.day_pnl_pct} />

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-4">
        <div className="lg:col-span-3">
          <EquityChart data={equitySeries} range={chartRange} onRangeChange={setChartRange} metric={chartMetric} onMetricChange={setChartMetric} />
        </div>
        <div>
          <LeftMetrics account={snapshot.account} pnl={pnlSummary} />
        </div>
      </div>

      {/* Bottom Content */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PositionsTable positions={snapshot.positions.list} />
        <TradesTable fills={fills} range={tradesRange} onRangeChange={setTradesRange} />
      </div>

      {/* Footer */}
      <footer className="mt-4 text-center text-xs text-gray-600">
        InspetorPro v2.0 | Equity: ${snapshot.account.equity.toFixed(2)} | {snapshot.positions.count} positions | Updated: {lastUpdate?.toLocaleTimeString('pt-BR')}
      </footer>
    </div>
  )
}
