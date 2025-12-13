import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const range = searchParams.get('range') || '7d'
  const symbol = searchParams.get('symbol') || ''
  const limit = searchParams.get('limit') || '200'
  
  const botBaseUrl = process.env.BOT_SNAPSHOT_URL?.replace('/api/snapshot', '') || ''
  const apiKey = process.env.BOT_API_KEY

  if (!botBaseUrl) {
    return NextResponse.json({ error: 'BOT_SNAPSHOT_URL not configured', fills: [] }, { status: 500 })
  }

  try {
    let url = `${botBaseUrl}/api/fills?range=${range}&limit=${limit}`
    if (symbol) url += `&symbol=${symbol}`
    
    const response = await fetch(url, {
      method: 'GET',
      headers: { 'X-API-KEY': apiKey || '', 'Content-Type': 'application/json' },
      cache: 'no-store',
    })

    if (!response.ok) {
      return NextResponse.json({ error: `Bot API error: ${response.status}`, fills: [] }, { status: response.status })
    }

    const data = await response.json()
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate' } })
  } catch (error) {
    console.error('Error fetching fills:', error)
    return NextResponse.json({ error: 'Failed to fetch fills', fills: [] }, { status: 500 })
  }
}
