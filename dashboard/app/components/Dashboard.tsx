'use client'

import { useState, useEffect } from 'react'
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts'

// Types
interface Position {
  symbol: string
  side: string
  size: number
  entry_price: number
  current_price: number
  pnl_pct: number
  pnl_usd?: number
  leverage: number
  stop_loss_price?: number
  take_profit_price?: number
}

interface BotSnapshot {
  timestamp_utc: string
  execution: {
    mode: string
    trading_mode: string
    is_paused: boolean
    live_trading: boolean
  }
  account: {
    equity: number
    free_margin: number
    day_pnl_pct: number
    week_pnl_pct?: number
  }
  positions: {
    count: number
    list: Position[]
    total_pnl_usd: number
  }
  ai_budget: {
    claude_calls_today: number
    claude_limit_per_day: number
    openai_calls_today: number
    openai_limit_per_day: number
    budget_ok: boolean
  }
  global_ia: {
    enabled: boolean
    last_call_time?: string
    last_call_minutes_ago?: number
  }
}

interface SeriesPoint {
  ts: string
  equity: number
  day_pnl_pct: number
}

interface Metrics {
  total_trades?: number
  wins?: number
  losses?: number
  win_rate?: number
  profit_factor?: number
  avg_win?: number
  avg_loss?: number
  net_pnl?: number
}

// Card component
function Card({ title, children, className = '' }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-dark-700 rounded-xl border border-dark-500 p-6 ${className}`}>
      {title && <div className="text-sm font-medium text-neutral mb-2">{title}</div>}
      {children}
    </div>
  )
}

// Stat card
function StatCard({ title, value, suffix = '', pnl = false }: { title: string; value: number | string; suffix?: string; pnl?: boolean }) {
  const numValue = typeof value === 'number' ? value : parseFloat(value) || 0
  const colorClass = pnl ? (numValue > 0 ? 'text-profit' : numValue < 0 ? 'text-loss' : 'text-neutral') : 'text-white'
  const displayValue = typeof value === 'number' 
    ? (pnl ? `${value >= 0 ? '+' : ''}${value.toFixed(2)}` : value.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
    : value

  return (
    <Card title={title}>
      <div className={`text-2xl font-bold ${colorClass}`}>{displayValue}{suffix}</div>
    </Card>
  )
}

// Equity Chart
function EquityChart({ data, range }: { data: SeriesPoint[]; range: string }) {
  if (!data || data.length === 0) {
    return (
      <Card title="📈 Equity Curve">
        <div className="h-64 flex items-center justify-center text-neutral">Sem dados disponíveis</div>
      </Card>
    )
  }

  const chartData = data.map(point => ({
    time: new Date(point.ts).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
    equity: point.equity
  }))

  return (
    <Card title={`📈 Equity Curve (${range})`}>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis dataKey="time" stroke="#666" tick={{ fill: '#888', fontSize: 11 }} />
            <YAxis stroke="#666" tick={{ fill: '#888', fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
            <Tooltip 
              contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333', borderRadius: '8px' }}
              formatter={(value: number) => [`$${value.toFixed(2)}`, 'Equity']}
            />
            <Area type="monotone" dataKey="equity" stroke="#3b82f6" fill="url(#colorEquity)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

// Metrics panel
function MetricsPanel({ metrics, range }: { metrics: Metrics; range: string }) {
  if (!metrics || Object.keys(metrics).length === 0) {
    return (
      <Card title={`📊 Métricas (${range})`}>
        <div className="text-neutral text-center py-4">Sem métricas disponíveis</div>
      </Card>
    )
  }

  return (
    <Card title={`📊 Métricas (${range})`}>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs text-neutral">Win Rate</div>
          <div className={`text-lg font-medium ${(metrics.win_rate || 0) >= 50 ? 'text-profit' : 'text-loss'}`}>
            {metrics.win_rate?.toFixed(1) || '—'}%
          </div>
        </div>
        <div>
          <div className="text-xs text-neutral">Profit Factor</div>
          <div className={`text-lg font-medium ${(metrics.profit_factor || 0) >= 1 ? 'text-profit' : 'text-loss'}`}>
            {metrics.profit_factor?.toFixed(2) || '—'}
          </div>
        </div>
        <div>
          <div className="text-xs text-neutral">Trades</div>
          <div className="text-lg font-medium">{metrics.total_trades || 0}</div>
        </div>
        <div>
          <div className="text-xs text-neutral">Net PnL</div>
          <div className={`text-lg font-medium ${(metrics.net_pnl || 0) >= 0 ? 'text-profit' : 'text-loss'}`}>
            ${metrics.net_pnl?.toFixed(2) || '0.00'}
          </div>
        </div>
        <div>
          <div className="text-xs text-neutral">Avg Win</div>
          <div className="text-lg font-medium text-profit">${metrics.avg_win?.toFixed(2) || '0.00'}</div>
        </div>
        <div>
          <div className="text-xs text-neutral">Avg Loss</div>
          <div className="text-lg font-medium text-loss">${metrics.avg_loss?.toFixed(2) || '0.00'}</div>
        </div>
      </div>
    </Card>
  )
}

// Positions table
function PositionsTable({ positions }: { positions: Position[] }) {
  if (!positions || positions.length === 0) {
    return (
      <Card title="Posições Abertas">
        <div className="text-neutral text-center py-8">Nenhuma posição aberta</div>
      </Card>
    )
  }

  return (
    <Card title={`Posições Abertas (${positions.length})`}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-neutral border-b border-dark-500">
              <th className="text-left py-3 px-2">Symbol</th>
              <th className="text-left py-3 px-2">Side</th>
              <th className="text-right py-3 px-2">Size</th>
              <th className="text-right py-3 px-2">Entry</th>
              <th className="text-right py-3 px-2">Price</th>
              <th className="text-right py-3 px-2">PnL %</th>
              <th className="text-right py-3 px-2">Lev</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos, i) => (
              <tr key={i} className="border-b border-dark-600 hover:bg-dark-600">
                <td className="py-3 px-2 font-medium">{pos.symbol}</td>
                <td className={`py-3 px-2 ${pos.side === 'long' ? 'text-profit' : 'text-loss'}`}>
                  {pos.side.toUpperCase()}
                </td>
                <td className="py-3 px-2 text-right">{pos.size}</td>
                <td className="py-3 px-2 text-right">${pos.entry_price?.toFixed(2)}</td>
                <td className="py-3 px-2 text-right">${pos.current_price?.toFixed(2)}</td>
                <td className={`py-3 px-2 text-right font-medium ${pos.pnl_pct >= 0 ? 'text-profit' : 'text-loss'}`}>
                  {pos.pnl_pct >= 0 ? '+' : ''}{pos.pnl_pct?.toFixed(2)}%
                </td>
                <td className="py-3 px-2 text-right">{pos.leverage}x</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

// AI Status panel
function AIStatusPanel({ globalIa, aiBudget }: { globalIa: BotSnapshot['global_ia']; aiBudget: BotSnapshot['ai_budget'] }) {
  return (
    <Card title="🧠 GLOBAL_IA Status">
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-neutral">Status</span>
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${globalIa.enabled ? 'bg-profit/20 text-profit' : 'bg-neutral/20 text-neutral'}`}>
            {globalIa.enabled ? '✅ ATIVO' : '❌ INATIVO'}
          </span>
        </div>
        
        {globalIa.last_call_minutes_ago !== undefined && (
          <div className="flex items-center justify-between">
            <span className="text-neutral">Última chamada</span>
            <span className="text-white">{globalIa.last_call_minutes_ago?.toFixed(1)} min atrás</span>
          </div>
        )}
        
        <div className="border-t border-dark-500 pt-4">
          <div className="text-neutral text-sm mb-2">AI Budget</div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-xs text-neutral">Claude</div>
              <div className="text-lg font-medium">{aiBudget?.claude_calls_today || 0}/{aiBudget?.claude_limit_per_day || 12}</div>
              <div className="w-full bg-dark-500 rounded-full h-2 mt-1">
                <div className="bg-purple-500 h-2 rounded-full" style={{ width: `${Math.min(100, ((aiBudget?.claude_calls_today || 0) / (aiBudget?.claude_limit_per_day || 12)) * 100)}%` }} />
              </div>
            </div>
            <div>
              <div className="text-xs text-neutral">OpenAI</div>
              <div className="text-lg font-medium">{aiBudget?.openai_calls_today || 0}/{aiBudget?.openai_limit_per_day || 40}</div>
              <div className="w-full bg-dark-500 rounded-full h-2 mt-1">
                <div className="bg-cyan-500 h-2 rounded-full" style={{ width: `${Math.min(100, ((aiBudget?.openai_calls_today || 0) / (aiBudget?.openai_limit_per_day || 40)) * 100)}%` }} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}

// Range selector
function RangeSelector({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ranges = ['1h', '24h', '7d', '30d']
  return (
    <div className="flex gap-2">
      {ranges.map(r => (
        <button
          key={r}
          onClick={() => onChange(r)}
          className={`px-3 py-1 rounded text-sm ${value === r ? 'bg-blue-500 text-white' : 'bg-dark-600 text-neutral hover:bg-dark-500'}`}
        >
          {r.toUpperCase()}
        </button>
      ))}
    </div>
  )
}

// Status badge - FONTE ÚNICA: execution_mode
function StatusBadge({ mode, paused }: { mode: string; paused: boolean }) {
  if (paused) return <span className="px-3 py-1 rounded-full bg-yellow-500/20 text-yellow-500 text-sm">⏸️ PAUSADO</span>
  
  // Normaliza o modo
  const normalizedMode = mode?.toUpperCase() || 'UNKNOWN'
  
  const colors: Record<string, string> = {
    'LIVE': 'bg-red-500/20 text-red-400',
    'PAPER_ONLY': 'bg-blue-500/20 text-blue-400',
    'PAPER': 'bg-blue-500/20 text-blue-400',
    'SHADOW': 'bg-purple-500/20 text-purple-400',
  }
  
  const icons: Record<string, string> = {
    'LIVE': '🔴',
    'PAPER_ONLY': '🟢',
    'PAPER': '🟢',
    'SHADOW': '🟣',
  }
  
  const displayMode = normalizedMode === 'PAPER_ONLY' ? 'PAPER' : normalizedMode
  const icon = icons[normalizedMode] || '⚪'
  
  return (
    <span className={`px-3 py-1 rounded-full text-sm font-medium ${colors[normalizedMode] || 'bg-neutral/20 text-neutral'}`}>
      {icon} {displayMode}
    </span>
  )
}

// Main dashboard
export function Dashboard() {
  const [snapshot, setSnapshot] = useState<BotSnapshot | null>(null)
  const [series, setSeries] = useState<SeriesPoint[]>([])
  const [metrics, setMetrics] = useState<Metrics>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const [range, setRange] = useState('24h')

  const fetchSnapshot = async () => {
    try {
      const res = await fetch('/api/bot-snapshot', { cache: 'no-store' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (data.error) throw new Error(data.error)
      setSnapshot(data)
      setError(null)
      setLastUpdate(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro desconhecido')
    } finally {
      setLoading(false)
    }
  }

  const fetchSeries = async () => {
    try {
      const res = await fetch(`/api/bot-series?range=${range}`, { cache: 'no-store' })
      if (res.ok) {
        const data = await res.json()
        setSeries(data.data || [])
      }
    } catch (err) {
      console.error('Error fetching series:', err)
    }
  }

  const fetchMetrics = async () => {
    try {
      const res = await fetch(`/api/bot-metrics?range=${range}`, { cache: 'no-store' })
      if (res.ok) {
        const data = await res.json()
        setMetrics(data.metrics || {})
      }
    } catch (err) {
      console.error('Error fetching metrics:', err)
    }
  }

  useEffect(() => {
    fetchSnapshot()
    fetchSeries()
    fetchMetrics()
    const interval = setInterval(() => { fetchSnapshot(); fetchSeries() }, 30000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    fetchSeries()
    fetchMetrics()
  }, [range])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-6 text-center">
        <div className="text-red-500 text-lg mb-2">❌ Erro</div>
        <div className="text-neutral">{error}</div>
      </div>
    )
  }

  if (!snapshot) return <div className="text-center text-neutral">Nenhum dado recebido</div>

  return (
    <div className="min-h-screen bg-dark-900 p-6">
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">🤖 IA Trading Dashboard</h1>
          <p className="text-neutral text-sm mt-1">Monitoramento em tempo real</p>
        </div>
        <div className="flex items-center gap-4">
          <RangeSelector value={range} onChange={setRange} />
          <StatusBadge mode={snapshot.execution.mode} paused={snapshot.execution.is_paused} />
          {lastUpdate && <span className="text-xs text-neutral">{lastUpdate.toLocaleTimeString('pt-BR')}</span>}
        </div>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard title="💰 Equity" value={snapshot.account.equity} suffix=" USD" />
        <StatCard title="📈 PnL Hoje" value={snapshot.account.day_pnl_pct} suffix="%" pnl />
        <StatCard 
          title="💵 Margem Livre" 
          value={
            snapshot.execution.mode === 'PAPER_ONLY' || snapshot.execution.mode === 'PAPER'
              ? (snapshot.account.free_margin > 0 ? snapshot.account.free_margin : snapshot.account.available_balance || snapshot.account.equity * 0.8)
              : (snapshot.account.free_margin > 0 ? snapshot.account.free_margin : snapshot.account.available_balance || 0)
          } 
          suffix=" USD" 
        />
        <StatCard title="📊 Posições" value={snapshot.positions.count} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="lg:col-span-2"><EquityChart data={series} range={range} /></div>
        <div><MetricsPanel metrics={metrics} range={range} /></div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2"><PositionsTable positions={snapshot.positions.list} /></div>
        <div><AIStatusPanel globalIa={snapshot.global_ia} aiBudget={snapshot.ai_budget} /></div>
      </div>

      <footer className="mt-8 text-center text-neutral text-sm">
        <p>AI Mode: {snapshot.execution.trading_mode} | Execution: {snapshot.execution.mode}</p>
        <p className="mt-1">
          {snapshot.execution.mode === 'LIVE' 
            ? '🔴 LIVE TRADING (Ordens Reais)' 
            : snapshot.execution.mode === 'SHADOW'
            ? '🟣 SHADOW MODE (Simulação + Sinais)'
            : '🟢 PAPER MODE (Simulação)'
          }
        </p>
      </footer>
    </div>
  )
}
