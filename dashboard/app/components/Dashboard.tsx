'use client'

import { useState, useEffect } from 'react'

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
    last_analysis?: string
    last_actions_count?: number
  }
  risk?: {
    max_positions: number
    open_positions: number
    circuit_breaker_active: boolean
  }
}

// Card component
export function Card({ 
  title, 
  children, 
  className = '' 
}: { 
  title?: string
  children: React.ReactNode
  className?: string 
}) {
  return (
    <div className={`card ${className}`}>
      {title && <div className="card-header">{title}</div>}
      {children}
    </div>
  )
}

// Stat card
export function StatCard({ 
  title, 
  value, 
  suffix = '', 
  pnl = false 
}: { 
  title: string
  value: number | string
  suffix?: string
  pnl?: boolean
}) {
  const numValue = typeof value === 'number' ? value : parseFloat(value) || 0
  const colorClass = pnl 
    ? numValue > 0 ? 'pnl-positive' : numValue < 0 ? 'pnl-negative' : 'pnl-neutral'
    : 'text-white'
  
  const displayValue = typeof value === 'number' 
    ? (pnl ? `${value >= 0 ? '+' : ''}${value.toFixed(2)}` : value.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
    : value

  return (
    <Card title={title}>
      <div className={`card-value ${colorClass}`}>
        {displayValue}{suffix}
      </div>
    </Card>
  )
}

// Positions table
export function PositionsTable({ positions }: { positions: Position[] }) {
  if (!positions || positions.length === 0) {
    return (
      <Card title="Posições Abertas">
        <div className="text-neutral text-center py-8">
          Nenhuma posição aberta
        </div>
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
                <td className={`py-3 px-2 text-right font-medium ${pos.pnl_pct >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
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
export function AIStatusPanel({ globalIa, aiBudget }: { globalIa: BotSnapshot['global_ia'], aiBudget: BotSnapshot['ai_budget'] }) {
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
              <div className="text-lg font-medium">
                {aiBudget?.claude_calls_today || 0}/{aiBudget?.claude_limit_per_day || 12}
              </div>
              <div className="w-full bg-dark-500 rounded-full h-2 mt-1">
                <div 
                  className="bg-accent-purple h-2 rounded-full" 
                  style={{ width: `${Math.min(100, ((aiBudget?.claude_calls_today || 0) / (aiBudget?.claude_limit_per_day || 12)) * 100)}%` }}
                />
              </div>
            </div>
            <div>
              <div className="text-xs text-neutral">OpenAI</div>
              <div className="text-lg font-medium">
                {aiBudget?.openai_calls_today || 0}/{aiBudget?.openai_limit_per_day || 40}
              </div>
              <div className="w-full bg-dark-500 rounded-full h-2 mt-1">
                <div 
                  className="bg-accent-cyan h-2 rounded-full" 
                  style={{ width: `${Math.min(100, ((aiBudget?.openai_calls_today || 0) / (aiBudget?.openai_limit_per_day || 40)) * 100)}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}

// Status badge
export function StatusBadge({ mode, paused }: { mode: string, paused: boolean }) {
  if (paused) {
    return <span className="px-3 py-1 rounded-full bg-yellow-500/20 text-yellow-500 text-sm">⏸️ PAUSADO</span>
  }
  
  const colors: Record<string, string> = {
    'LIVE': 'bg-profit/20 text-profit',
    'PAPER_ONLY': 'bg-accent-blue/20 text-accent-blue',
    'SHADOW': 'bg-accent-purple/20 text-accent-purple',
  }
  
  return (
    <span className={`px-3 py-1 rounded-full text-sm font-medium ${colors[mode] || 'bg-neutral/20 text-neutral'}`}>
      {mode}
    </span>
  )
}

// Loading spinner
export function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-accent-blue"></div>
    </div>
  )
}

// Error message
export function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="bg-loss/10 border border-loss/20 rounded-xl p-6 text-center">
      <div className="text-loss text-lg mb-2">❌ Erro</div>
      <div className="text-neutral">{message}</div>
    </div>
  )
}

// Main dashboard component
export function Dashboard() {
  const [snapshot, setSnapshot] = useState<BotSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  const fetchSnapshot = async () => {
    try {
      const res = await fetch('/api/bot-snapshot', { cache: 'no-store' })
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }
      const data = await res.json()
      if (data.error) {
        throw new Error(data.error)
      }
      setSnapshot(data)
      setError(null)
      setLastUpdate(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro desconhecido')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSnapshot()
    // Atualiza a cada 30 segundos
    const interval = setInterval(fetchSnapshot, 30000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return <LoadingSpinner />
  }

  if (error) {
    return <ErrorMessage message={error} />
  }

  if (!snapshot) {
    return <ErrorMessage message="Nenhum dado recebido" />
  }

  return (
    <div className="min-h-screen bg-dark-900 p-6">
      {/* Header */}
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">🤖 IA Trading Dashboard</h1>
          <p className="text-neutral text-sm mt-1">
            Monitoramento em tempo real do bot de trading
          </p>
        </div>
        <div className="flex items-center gap-4">
          <StatusBadge 
            mode={snapshot.execution.mode} 
            paused={snapshot.execution.is_paused} 
          />
          {lastUpdate && (
            <span className="text-xs text-neutral">
              Atualizado: {lastUpdate.toLocaleTimeString('pt-BR')}
            </span>
          )}
        </div>
      </header>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard 
          title="💰 Equity" 
          value={snapshot.account.equity} 
          suffix=" USD"
        />
        <StatCard 
          title="📈 PnL Hoje" 
          value={snapshot.account.day_pnl_pct} 
          suffix="%"
          pnl
        />
        <StatCard 
          title="💵 Margem Livre" 
          value={snapshot.account.free_margin} 
          suffix=" USD"
        />
        <StatCard 
          title="📊 Posições" 
          value={snapshot.positions.count} 
        />
      </div>

      {/* Main content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Positions - 2 cols */}
        <div className="lg:col-span-2">
          <PositionsTable positions={snapshot.positions.list} />
        </div>

        {/* AI Status - 1 col */}
        <div>
          <AIStatusPanel 
            globalIa={snapshot.global_ia} 
            aiBudget={snapshot.ai_budget} 
          />
        </div>
      </div>

      {/* Footer */}
      <footer className="mt-8 text-center text-neutral text-sm">
        <p>Trading Mode: {snapshot.execution.trading_mode}</p>
        <p className="mt-1">
          {snapshot.execution.live_trading ? '🔴 LIVE TRADING' : '🟢 PAPER TRADING'}
        </p>
      </footer>
    </div>
  )
}
