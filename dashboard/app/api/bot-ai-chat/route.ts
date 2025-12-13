import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export async function POST(request: Request) {
  const botUrl = process.env.BOT_SNAPSHOT_URL?.replace('/api/snapshot', '/api/ai-chat') || 'http://localhost:8080/api/ai-chat'
  const apiKey = process.env.BOT_API_KEY || ''

  try {
    const body = await request.json()
    
    const response = await fetch(botUrl, {
      method: 'POST',
      headers: {
        'X-API-KEY': apiKey,
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      },
      body: JSON.stringify(body),
      cache: 'no-store',
    })

    if (!response.ok) {
      return NextResponse.json({ reply: 'Erro ao conectar com a IA', error: 'Failed to fetch' })
    }

    const data = await response.json()
    return NextResponse.json(data, {
      headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate' }
    })
  } catch (error) {
    console.error('Error in AI chat:', error)
    return NextResponse.json({ reply: 'Erro de conexão', error: 'Connection failed' })
  }
}
