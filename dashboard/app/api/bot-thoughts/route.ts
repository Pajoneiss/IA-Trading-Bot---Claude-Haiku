import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export async function GET() {
  const botUrl = process.env.BOT_SNAPSHOT_URL?.replace('/api/snapshot', '/api/thoughts') || 'http://localhost:8080/api/thoughts'
  const apiKey = process.env.BOT_API_KEY || ''

  try {
    const response = await fetch(`${botUrl}?limit=20`, {
      method: 'GET',
      headers: {
        'X-API-KEY': apiKey,
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      },
      cache: 'no-store',
    })

    if (!response.ok) {
      return NextResponse.json({ thoughts: [], error: 'Failed to fetch thoughts' })
    }

    const data = await response.json()
    return NextResponse.json(data, {
      headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate' }
    })
  } catch (error) {
    console.error('Error fetching thoughts:', error)
    return NextResponse.json({ thoughts: [], error: 'Connection failed' })
  }
}
