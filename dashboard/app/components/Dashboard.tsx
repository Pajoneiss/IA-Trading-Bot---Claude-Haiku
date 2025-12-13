'use client'
import { useState, useEffect, useCallback, useRef } from 'react'
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, ReferenceDot, LineChart, Line } from 'recharts'

// Types
interface Position { symbol: string; side: string; size: number; entry_price: number; current_price: number; pnl_pct: number; leverage: number; liquidation_px?: number }
interface AccountInfo { equity: number; account_value: number; free_margin: number; withdrawable: number; used_margin: number; position_value: number; unrealized_pnl: number; leverage: number; long_exposure: number; short_exposure: number; roe_pct: number; direction_bias: string; margin_usage_pct: number; day_pnl_pct: number }
interface BotSnapshot { timestamp_utc: string; execution: { mode: string; trading_mode: string; is_paused: boolean }; account: AccountInfo; positions: { count: number; list: Position[]; total_pnl_usd: number }; ai_budget: { claude_calls_today: number; claude_limit_per_day: number; openai_calls_today: number; openai_limit_per_day: number }; global_ia: { enabled: boolean; last_call_minutes_ago?: number } }
interface PnLSummary { current_equity: number; pnl_all_time_pct: number; pnl_all_time_usd: number; pnl_day_pct: number; pnl_day_usd: number; pnl_week_pct: number; pnl_week_usd: number; pnl_month_pct: number; pnl_month_usd: number; winrate: number; profit_factor: number; max_drawdown_pct: number; total_trades: number }
interface EquityPoint { ts: string; equity_usd: number }
interface Fill { id: number; ts: string; symbol: string; side: string; qty: number; price: number; realized_pnl: number; fee: number }
interface Thought { id: string; timestamp: string; type: string; summary: string; symbols: string[]; actions: string[]; confidence?: number }
interface ChatMessage { role: 'user' | 'assistant'; content: string; timestamp: Date }

// Card Components
const Card = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <div className={`bg-[#1a1a1a] rounded-lg border border-[#2a2a2a] p-4 ${className}`}>{children}</div>
)

// Top Stats Bar
const TopStats = ({ account }: { account: AccountInfo }) => (
  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2 mb-3">
    <Card className="p-3"><div className="text-[10px] text-gray-500 uppercase">Total Value</div><div className="text-lg font-bold">{account.account_value.toFixed(2)}</div></Card>
    <Card className="p-3"><div className="text-[10px] text-gray-500 uppercase">Withdrawable</div><div className="text-lg font-bold text-[#00ff88]">{account.withdrawable.toFixed(2)}</div></Card>
    <Card className="p-3"><div className="text-[10px] text-gray-500 uppercase">Leverage</div><div className="text-lg font-bold">{account.leverage.toFixed(2)}x</div></Card>
    <Card className="p-3"><div className="text-[10px] text-gray-500 uppercase">Position Value</div><div className="text-lg font-bold">{account.position_value.toFixed(2)}</div></Card>
    <Card className="p-3"><div className="text-[10px] text-gray-500 uppercase">Unrealized PnL</div><div className={`text-lg font-bold ${account.unrealized_pnl >= 0 ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{account.unrealized_pnl.toFixed(2)}</div></Card>
    <Card className="p-3"><div className="text-[10px] text-gray-500 uppercase">ROE</div><div className={`text-lg font-bold ${account.roe_pct >= 0 ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{account.roe_pct.toFixed(2)}%</div></Card>
    <Card className="p-3">
      <div className="text-[10px] text-gray-500 uppercase">Direction Bias</div>
      <div className={`font-bold ${account.direction_bias === 'LONG' ? 'text-[#00ff88]' : account.direction_bias === 'SHORT' ? 'text-[#ff4d4d]' : 'text-gray-400'}`}>
        {account.direction_bias === 'LONG' ? '↗ LONG' : account.direction_bias === 'SHORT' ? '↘ SHORT' : '→ NEUTRAL'}
      </div>
      <div className="flex gap-1 mt-1">
        <div className="h-1 rounded-full bg-[#00ff88]" style={{ width: `${account.long_exposure}%` }} />
        <div className="h-1 rounded-full bg-[#ff4d4d]" style={{ width: `${account.short_exposure}%` }} />
      </div>
    </Card>
  </div>
)

// Sparkline Component
const Sparkline = ({ data, color }: { data: number[]; color: string }) => {
  if (!data || data.length < 2) return null
  const chartData = data.map((v, i) => ({ x: i, y: v }))
  return (
    <div className="h-8 w-full mt-1">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <Line type="monotone" dataKey="y" stroke={color} strokeWidth={1.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

// Tooltip Component
const InfoTooltip = ({ text }: { text: string }) => {
  const [show, setShow] = useState(false)
  return (
    <div className="relative inline-block">
      <button
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        className="ml-1 text-[10px] text-gray-500 hover:text-[#00b8ff] cursor-help"
      >
        ℹ️
      </button>
      {show && (
        <div className="absolute z-10 bottom-full left-0 mb-1 w-48 p-2 bg-[#1a1a1a] border border-[#2a2a2a] rounded text-[10px] text-gray-300 shadow-lg">
          {text}
        </div>
      )}
    </div>
  )
}

// PnL Cards
const PnLCards = ({ pnl, equitySeries }: { pnl: PnLSummary | null; equitySeries: EquityPoint[] }) => {
  const now = new Date()
  const getSparklineData = (hours: number) => {
    if (!equitySeries.length) return []
    const cutoff = new Date(now.getTime() - hours * 60 * 60 * 1000)
    return equitySeries.filter(p => new Date(p.ts) >= cutoff).map(p => p.equity_usd)
  }

  const cards = [
    {
      label: '🏆 ALL TIME',
      pct: pnl?.pnl_all_time_pct || 0,
      usd: pnl?.pnl_all_time_usd || 0,
      highlight: true,
      sparkline: equitySeries.map(p => p.equity_usd),
      tooltip: 'Lucro/Prejuízo total desde o início. Mostra quanto sua conta cresceu ou diminuiu desde a primeira operação.',
      since: 'desde o início'
    },
    {
      label: '📅 24H',
      pct: pnl?.pnl_day_pct || 0,
      usd: pnl?.pnl_day_usd || 0,
      sparkline: getSparklineData(24),
      tooltip: 'Variação nas últimas 24 horas. Mostra o desempenho do bot no dia atual.',
      since: 'últimas 24h'
    },
    {
      label: '📆 7D',
      pct: pnl?.pnl_week_pct || 0,
      usd: pnl?.pnl_week_usd || 0,
      sparkline: getSparklineData(168),
      tooltip: 'Variação nos últimos 7 dias. Mostra a tendência semanal do bot.',
      since: 'últimos 7 dias'
    },
    {
      label: '🗓️ 30D',
      pct: pnl?.pnl_month_pct || 0,
      usd: pnl?.pnl_month_usd || 0,
      sparkline: getSparklineData(720),
      tooltip: 'Variação nos últimos 30 dias. Mostra o desempenho mensal do bot.',
      since: 'últimos 30 dias'
    },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
      {cards.map((c, i) => {
        const color = c.pct >= 0 ? '#00ff88' : '#ff4d4d'
        return (
          <Card key={i} className={`p-3 relative ${c.highlight ? (c.pct >= 0 ? 'border-[#00ff88]/30 bg-[#00ff88]/5 shadow-lg shadow-[#00ff88]/10' : 'border-[#ff4d4d]/30 bg-[#ff4d4d]/5 shadow-lg shadow-[#ff4d4d]/10') : 'hover:border-[#2a2a2a]/60 transition-all'}`}>
            <div className="flex items-center justify-between">
              <div className="text-xs text-gray-500">{c.label}</div>
              <InfoTooltip text={c.tooltip} />
            </div>
            <div className={`text-2xl font-bold ${color === '#00ff88' ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>
              {c.pct >= 0 ? '+' : ''}{c.pct.toFixed(2)}%
            </div>
            <div className={`text-sm ${color === '#00ff88' ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>
              {c.pct >= 0 ? '+' : ''}${c.usd.toFixed(2)}
            </div>
            <Sparkline data={c.sparkline} color={color} />
            <div className="text-[9px] text-gray-600 mt-1">{c.since}</div>
            <div className="absolute top-2 right-2">
              <span className="px-1.5 py-0.5 rounded text-[8px] bg-[#00b8ff]/20 text-[#00b8ff]">Live</span>
            </div>
          </Card>
        )
      })}
    </div>
  )
}

// Equity Chart
const EquityChart = ({ data, range, onRangeChange }: { data: EquityPoint[]; range: string; onRangeChange: (r: string) => void }) => {
  if (!data?.length) return <Card className="h-64"><div className="h-full flex items-center justify-center text-gray-500">Carregando...</div></Card>
  const chartData = data.map(p => ({ time: new Date(p.ts).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }), value: p.equity_usd }))
  const vals = data.map(d => d.equity_usd)
  const min = Math.min(...vals), max = Math.max(...vals)
  const last = vals[vals.length - 1] || 0, first = vals[0] || 0
  const pnl = last - first, color = pnl >= 0 ? '#00ff88' : '#ff4d4d'
  return (
    <Card className="h-64">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <span className="text-sm">Perp Equity</span>
          <span className="text-lg font-bold">${last.toFixed(2)}</span>
        </div>
        <div className="flex gap-1">
          {['24H', '1W', '1M', 'All'].map(r => <button key={r} onClick={() => onRangeChange(r === '24H' ? '1d' : r === '1W' ? '7d' : r === '1M' ? '30d' : 'all')} className={`px-2 py-0.5 rounded text-xs ${(range === '1d' && r === '24H') || (range === '7d' && r === '1W') || (range === '30d' && r === '1M') || (range === 'all' && r === 'All') ? 'bg-[#00b8ff] text-white' : 'bg-[#2a2a2a] text-gray-400'}`}>{r}</button>)}
        </div>
      </div>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs><linearGradient id="grad" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={color} stopOpacity={0.3} /><stop offset="95%" stopColor={color} stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
            <XAxis dataKey="time" stroke="#666" tick={{ fill: '#666', fontSize: 9 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
            <YAxis stroke="#666" tick={{ fill: '#666', fontSize: 9 }} tickLine={false} axisLine={false} domain={[min * 0.99, max * 1.01]} tickFormatter={v => `$${v.toFixed(0)}`} width={45} />
            <Tooltip contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333', borderRadius: '8px', fontSize: '11px' }} formatter={(v: number) => [`$${v.toFixed(2)}`, 'Equity']} />
            <Area type="monotone" dataKey="value" stroke={color} fill="url(#grad)" strokeWidth={2} dot={false} />
            <ReferenceDot x={chartData[chartData.length - 1]?.time} y={last} r={3} fill={color} stroke="#1a1a1a" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="text-right text-xs mt-1 text-gray-500">{range.toUpperCase()} PnL: <span className={pnl >= 0 ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}>${pnl.toFixed(2)}</span></div>
    </Card>
  )
}

// Performance Metrics
const MetricsPanel = ({ pnl }: { pnl: PnLSummary | null }) => (
  <Card className="h-64">
    <div className="text-sm font-medium mb-3">📊 Performance</div>
    <div className="grid grid-cols-2 gap-3">
      <div><div className="text-[10px] text-gray-500">Win Rate</div><div className={`text-lg font-bold ${(pnl?.winrate || 0) >= 50 ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{pnl?.winrate?.toFixed(1) || 0}%</div></div>
      <div><div className="text-[10px] text-gray-500">Profit Factor</div><div className={`text-lg font-bold ${(pnl?.profit_factor || 0) >= 1 ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{pnl?.profit_factor?.toFixed(2) || 0}</div></div>
      <div><div className="text-[10px] text-gray-500">Max Drawdown</div><div className="text-lg font-bold text-[#ff4d4d]">-{pnl?.max_drawdown_pct?.toFixed(1) || 0}%</div></div>
      <div><div className="text-[10px] text-gray-500">Total Trades</div><div className="text-lg font-bold">{pnl?.total_trades || 0}</div></div>
    </div>
  </Card>
)

// Positions Table
const PositionsTable = ({ positions }: { positions: Position[] }) => (
  <Card>
    <div className="flex items-center justify-between mb-2">
      <span className="text-sm font-medium">Positions ({positions.length})</span>
      <span className="text-xs text-gray-500">Total ${positions.reduce((a, p) => a + (p.size * p.entry_price), 0).toFixed(2)}</span>
    </div>
    {!positions.length ? <div className="text-gray-500 text-center py-4 text-sm">Nenhuma posição</div> : (
      <div className="overflow-x-auto overflow-y-auto max-h-40">
        <table className="w-full text-xs">
          <thead><tr className="text-gray-500 border-b border-[#2a2a2a]">
            <th className="text-left py-1">Asset</th><th className="text-left py-1">Side</th><th className="text-right py-1">Size</th><th className="text-right py-1">Entry</th><th className="text-right py-1">PnL</th>
          </tr></thead>
          <tbody>
            {positions.map((p, i) => (
              <tr key={i} className="border-b border-[#2a2a2a]/50">
                <td className="py-1">{p.symbol}</td>
                <td className={`py-1 ${p.side === 'long' ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{p.side?.toUpperCase()}</td>
                <td className="py-1 text-right">{p.size} ({p.leverage}x)</td>
                <td className="py-1 text-right">${p.entry_price?.toFixed(2)}</td>
                <td className={`py-1 text-right ${p.pnl_pct >= 0 ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{p.pnl_pct >= 0 ? '+' : ''}{p.pnl_pct?.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </Card>
)

// Trades Table
const TradesTable = ({ fills, range, onRangeChange }: { fills: Fill[]; range: string; onRangeChange: (r: string) => void }) => (
  <Card>
    <div className="flex items-center justify-between mb-2">
      <span className="text-sm font-medium">Recent Fills ({fills.length})</span>
      <div className="flex gap-1">
        {['7d', '30d', 'all'].map(r => <button key={r} onClick={() => onRangeChange(r)} className={`px-2 py-0.5 rounded text-xs ${range === r ? 'bg-[#00b8ff] text-white' : 'bg-[#2a2a2a] text-gray-400'}`}>{r.toUpperCase()}</button>)}
      </div>
    </div>
    {!fills.length ? <div className="text-gray-500 text-center py-4 text-sm">Nenhum trade</div> : (
      <div className="overflow-x-auto overflow-y-auto max-h-40">
        <table className="w-full text-xs">
          <thead><tr className="text-gray-500 border-b border-[#2a2a2a]">
            <th className="text-left py-1">Time</th><th className="text-left py-1">Asset</th><th className="text-left py-1">Side</th><th className="text-right py-1">Price</th><th className="text-right py-1">PnL</th>
          </tr></thead>
          <tbody>
            {fills.slice(0, 10).map((f, i) => (
              <tr key={f.id || i} className="border-b border-[#2a2a2a]/50">
                <td className="py-1 text-gray-500">{new Date(f.ts).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</td>
                <td className="py-1">{f.symbol}</td>
                <td className={`py-1 ${f.side === 'buy' || f.side === 'long' || f.side === 'B' ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{f.side?.toUpperCase()}</td>
                <td className="py-1 text-right">${f.price?.toFixed(2)}</td>
                <td className={`py-1 text-right ${f.realized_pnl >= 0 ? 'text-[#00ff88]' : 'text-[#ff4d4d]'}`}>{f.realized_pnl !== 0 ? `${f.realized_pnl >= 0 ? '+' : ''}$${f.realized_pnl.toFixed(2)}` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </Card>
)

// AI Thought Feed
const ThoughtFeed = ({ thoughts }: { thoughts: Thought[] }) => {
  const typeEmoji: Record<string, string> = { analysis: '🔍', decision: '🎯', execution: '⚡', risk: '⚠️', adjustment: '🔧', error: '❌', insight: '💡', strategy: '📈' }
  return (
    <Card>
      <div className="text-sm font-medium mb-2">🧠 AI Thoughts</div>
      {!thoughts.length ? <div className="text-gray-500 text-center py-4 text-sm">Aguardando pensamentos...</div> : (
        <div className="space-y-2 max-h-48 overflow-y-auto">
          {thoughts.slice(0, 8).map(t => (
            <div key={t.id} className="p-2 bg-[#0d0d0d] rounded border border-[#2a2a2a]">
              <div className="flex items-center gap-2 mb-1">
                <span>{typeEmoji[t.type] || '💭'}</span>
                <span className="text-[10px] text-gray-500">{new Date(t.timestamp).toLocaleString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</span>
                {t.symbols?.length > 0 && <span className="text-[10px] text-[#00b8ff]">{t.symbols.join(', ')}</span>}
              </div>
              <div className="text-xs text-gray-300">{t.summary}</div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

// AI Chat
const AIChat = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const chatRef = useRef<HTMLDivElement>(null)

  const sendMessage = async () => {
    if (!input.trim() || loading) return
    const userMsg: ChatMessage = { role: 'user', content: input.trim(), timestamp: new Date() }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)
    try {
      const res = await fetch('/api/bot-ai-chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: input.trim() }) })
      const data = await res.json()
      const assistantMsg: ChatMessage = { role: 'assistant', content: data.reply || 'Sem resposta', timestamp: new Date() }
      setMessages(prev => [...prev, assistantMsg])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Erro ao conectar com a IA', timestamp: new Date() }])
    }
    setLoading(false)
  }

  useEffect(() => { chatRef.current?.scrollTo(0, chatRef.current.scrollHeight) }, [messages])

  return (
    <Card>
      <div className="text-sm font-medium mb-2">💬 Chat com IA</div>
      <div ref={chatRef} className="h-32 overflow-y-auto mb-2 space-y-2">
        {messages.length === 0 && <div className="text-gray-500 text-xs text-center py-4">Pergunte sobre posições, estratégia...</div>}
        {messages.map((m, i) => (
          <div key={i} className={`text-xs p-2 rounded ${m.role === 'user' ? 'bg-[#00b8ff]/20 ml-4' : 'bg-[#2a2a2a] mr-4'}`}>
            {m.content}
          </div>
        ))}
        {loading && <div className="text-xs text-gray-500 animate-pulse">Pensando...</div>}
      </div>
      <div className="flex gap-2">
        <input type="text" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && sendMessage()} placeholder="Pergunte algo..." className="flex-1 bg-[#0d0d0d] border border-[#2a2a2a] rounded px-2 py-1 text-xs focus:outline-none focus:border-[#00b8ff]" />
        <button onClick={sendMessage} disabled={loading} className="px-3 py-1 bg-[#00b8ff] text-white rounded text-xs hover:bg-[#00a0e0] disabled:opacity-50">Enviar</button>
      </div>
    </Card>
  )
}

// Daily Summary for Leigos
const DailySummary = ({ account, pnl }: { account: AccountInfo; pnl: PnLSummary | null }) => {
  const getRiskLevel = () => {
    const marginUsage = account.margin_usage_pct
    if (marginUsage > 70) return { level: 'Alto', color: 'text-[#ff4d4d]', bg: 'bg-[#ff4d4d]/10' }
    if (marginUsage > 40) return { level: 'Médio', color: 'text-yellow-400', bg: 'bg-yellow-400/10' }
    return { level: 'Baixo', color: 'text-[#00ff88]', bg: 'bg-[#00ff88]/10' }
  }
  const risk = getRiskLevel()
  const avgLeverage = account.leverage.toFixed(1)
  const posCount = account.position_value > 0 ? '3+' : '0' // Simplified

  return (
    <Card className="p-4 mb-3">
      <div className="text-sm font-medium mb-3">📊 Resumo do Dia</div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <div className="text-[10px] text-gray-500 uppercase mb-1">Status do Bot</div>
          <div className="text-xs text-gray-300">
            Hoje o bot está: <span className={account.direction_bias === 'LONG' ? 'text-[#00ff88] font-bold' : account.direction_bias === 'SHORT' ? 'text-[#ff4d4d] font-bold' : 'text-gray-400 font-bold'}>{account.direction_bias}</span>
          </div>
          <div className="text-xs text-gray-300 mt-1">
            Alavancagem média: <span className="font-bold">{avgLeverage}x</span> | Posições: <span className="font-bold">{posCount}</span>
          </div>
        </div>
        <div>
          <div className="text-[10px] text-gray-500 uppercase mb-1">Nível de Risco</div>
          <div className={`inline-block px-3 py-1 rounded ${risk.bg} ${risk.color} text-sm font-bold`}>
            {risk.level}
          </div>
          <div className="text-[10px] text-gray-500 mt-1">Margem usada: {account.margin_usage_pct.toFixed(0)}%</div>
        </div>
        <div>
          <div className="text-[10px] text-gray-500 uppercase mb-1">Objetivo</div>
          <div className="text-xs text-gray-300">
            {(pnl?.pnl_day_pct || 0) >= 0 ? '🎯 Proteger ganhos' : '🔄 Buscar recuperação'}
          </div>
          <div className="text-[10px] text-gray-500 mt-1">
            Equity: ${account.equity.toFixed(2)}
          </div>
        </div>
      </div>
    </Card>
  )
}

// Mode Toggle
const ModeToggle = ({ mode, onChange }: { mode: 'simple' | 'pro'; onChange: (m: 'simple' | 'pro') => void }) => (
  <div className="flex gap-1 bg-[#1a1a1a] rounded p-0.5 border border-[#2a2a2a]">
    <button
      onClick={() => onChange('simple')}
      className={`px-3 py-1 rounded text-xs transition-all ${mode === 'simple' ? 'bg-[#00b8ff] text-white' : 'text-gray-400 hover:text-white'}`}
    >
      Simples
    </button>
    <button
      onClick={() => onChange('pro')}
      className={`px-3 py-1 rounded text-xs transition-all ${mode === 'pro' ? 'bg-[#00b8ff] text-white' : 'text-gray-400 hover:text-white'}`}
    >
      Profissional
    </button>
  </div>
)

// Badge
const Badge = ({ mode, paused }: { mode: string; paused: boolean }) => {
  if (paused) return <span className="px-2 py-0.5 rounded text-xs bg-yellow-500/20 text-yellow-400">⏸️ PAUSED</span>
  const m = mode?.toUpperCase() || ''
  if (m.includes('LIVE')) return <span className="px-2 py-0.5 rounded text-xs bg-[#ff4d4d]/20 text-[#ff4d4d]">🔴 LIVE</span>
  if (m.includes('SHADOW')) return <span className="px-2 py-0.5 rounded text-xs bg-purple-500/20 text-purple-400">🟣 SHADOW</span>
  return <span className="px-2 py-0.5 rounded text-xs bg-[#00b8ff]/20 text-[#00b8ff]">🟢 PAPER</span>
}

// Main Dashboard
export function Dashboard() {
  const [snapshot, setSnapshot] = useState<BotSnapshot | null>(null)
  const [pnlSummary, setPnlSummary] = useState<PnLSummary | null>(null)
  const [equitySeries, setEquitySeries] = useState<EquityPoint[]>([])
  const [fills, setFills] = useState<Fill[]>([])
  const [thoughts, setThoughts] = useState<Thought[]>([])
  const [loading, setLoading] = useState(true)
  const [chartRange, setChartRange] = useState('7d')
  const [tradesRange, setTradesRange] = useState('7d')
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const [viewMode, setViewMode] = useState<'simple' | 'pro'>('simple')

  const fetchAll = useCallback(async () => {
    try {
      const [snapRes, pnlRes, seriesRes, fillsRes, thoughtsRes] = await Promise.all([
        fetch('/api/bot-snapshot', { cache: 'no-store' }),
        fetch('/api/bot-pnl-summary', { cache: 'no-store' }),
        fetch(`/api/bot-pnl-series?range=${chartRange}`, { cache: 'no-store' }),
        fetch(`/api/bot-fills?range=${tradesRange}`, { cache: 'no-store' }),
        fetch('/api/bot-thoughts', { cache: 'no-store' }).catch(() => ({ ok: false }))
      ])
      if (snapRes.ok) { const d = await snapRes.json(); if (!d.error) setSnapshot(d) }
      if (pnlRes.ok) { const d = await pnlRes.json(); if (!d.error) setPnlSummary(d) }
      if (seriesRes.ok) { const d = await seriesRes.json(); setEquitySeries(d.data || []) }
      if (fillsRes.ok) { const d = await fillsRes.json(); setFills(d.fills || []) }
      if (thoughtsRes.ok) { const d = await (thoughtsRes as Response).json(); setThoughts(d.thoughts || []) }
      setLastUpdate(new Date())
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }, [chartRange, tradesRange])

  useEffect(() => { fetchAll(); const i = setInterval(fetchAll, 10000); return () => clearInterval(i) }, [fetchAll])

  if (loading) return <div className="min-h-screen bg-[#0d0d0d] flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-t-2 border-[#00b8ff]" /></div>
  if (!snapshot) return <div className="min-h-screen bg-[#0d0d0d] flex items-center justify-center text-gray-500">Conectando ao bot...</div>

  return (
    <div className="min-h-screen bg-[#0d0d0d] text-white p-3">
      <header className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold">🤖 InspetorPro Dashboard</h1>
          <Badge mode={snapshot.execution.mode} paused={snapshot.execution.is_paused} />
          <ModeToggle mode={viewMode} onChange={setViewMode} />
        </div>
        <div className="text-xs text-gray-500">AI: {snapshot.execution.trading_mode} | Next refresh in {lastUpdate ? Math.max(0, 10 - Math.floor((Date.now() - lastUpdate.getTime()) / 1000)) : 10}s</div>
      </header>

      <TopStats account={snapshot.account} />
      <PnLCards pnl={pnlSummary} equitySeries={equitySeries} />
      {viewMode === 'simple' && <DailySummary account={snapshot.account} pnl={pnlSummary} />}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-3 mb-3">
        <div className="lg:col-span-3"><EquityChart data={equitySeries} range={chartRange} onRangeChange={setChartRange} /></div>
        <div><MetricsPanel pnl={pnlSummary} /></div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <PositionsTable positions={snapshot.positions.list} />
        <TradesTable fills={fills} range={tradesRange} onRangeChange={setTradesRange} />
        <ThoughtFeed thoughts={thoughts} />
        <AIChat />
      </div>

      <footer className="mt-3 text-center text-xs text-gray-600">
        InspetorPro v2.1 | Equity: ${snapshot.account.equity.toFixed(2)} | {snapshot.positions.count} positions | {lastUpdate?.toLocaleTimeString('pt-BR')}
      </footer>
    </div>
  )
}
