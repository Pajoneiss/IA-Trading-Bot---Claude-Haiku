import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export async function GET() {
  const botBaseUrl = process.env.BOT_SNAPSHOT_URL?.replace('/api/snapshot', '') || ''
  const apiKey = process.env.BOT_API_KEY

  if (!botBaseUrl) {
    return NextResponse.json({ error: 'BOT_SNAPSHOT_URL not configured' }, { status: 500 })
  }

  try {
    const response = await fetch(`${botBaseUrl}/api/pnl/summary`, {
      method: 'GET',
      headers: { 'X-API-KEY': apiKey || '', 'Content-Type': 'application/json' },
      cache: 'no-store',
    })

    if (!response.ok) {
      return NextResponse.json({ error: `Bot API error: ${response.status}` }, { status: response.status })
    }

    const data = await response.json()
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate' } })
  } catch (error) {
    console.error('Error fetching PnL summary:', error)
    return NextResponse.json({ error: 'Failed to fetch PnL summary' }, { status: 500 })
  }
}
