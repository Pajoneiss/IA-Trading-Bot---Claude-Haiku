# 🤖 IA Trading Dashboard

Dashboard em tempo real para monitoramento do bot de trading com IA.

## 🚀 Quick Start

### 1. Instalar dependências

```bash
cd dashboard
npm install
```

### 2. Configurar variáveis de ambiente

Crie um arquivo `.env.local`:

```env
BOT_SNAPSHOT_URL=https://seu-projeto.railway.app/api/snapshot
BOT_API_KEY=sua-api-key-do-railway
```

### 3. Rodar localmente

```bash
npm run dev
```

Acesse: http://localhost:3000

## 📦 Deploy na Vercel

### 1. Push para GitHub

```bash
# Se o dashboard estiver no mesmo repo do bot
git add dashboard/
git commit -m "Add dashboard"
git push
```

### 2. Conectar na Vercel

1. Acesse [vercel.com](https://vercel.com)
2. Clique em "New Project"
3. Importe seu repositório
4. Configure:
   - **Root Directory**: `dashboard`
   - **Framework**: Next.js

### 3. Configurar Environment Variables

Na Vercel, adicione:

| Variable | Value |
|----------|-------|
| `BOT_SNAPSHOT_URL` | `https://seu-projeto.railway.app/api/snapshot` |
| `BOT_API_KEY` | `sua-api-key-do-railway` |

### 4. Deploy!

A Vercel fará o deploy automaticamente.

## 🔧 Configuração do Bot (Railway)

Certifique-se de que o bot tem estas variáveis:

```env
DASHBOARD_API_KEY=mesma-key-que-na-vercel
API_PORT=8080
```

O bot expõe automaticamente:
- `GET /api/snapshot` - Snapshot completo
- `GET /api/health` - Health check
- `GET /api/positions` - Posições
- `GET /api/account` - Info da conta
- `GET /api/ai-status` - Status do GLOBAL_IA

## 📊 Features

- **Equity & PnL em tempo real**
- **Tabela de posições abertas**
- **Status do GLOBAL_IA**
- **AI Budget (Claude + OpenAI)**
- **Atualização automática a cada 30s**
- **Tema escuro trader-style**
- **Responsivo (mobile-friendly)**

## 🛠️ Estrutura

```
dashboard/
├── app/
│   ├── api/
│   │   └── bot-snapshot/
│   │       └── route.ts      # Proxy para API do bot
│   ├── components/
│   │   └── Dashboard.tsx     # Componentes do dashboard
│   ├── globals.css           # Estilos globais
│   ├── layout.tsx            # Layout base
│   └── page.tsx              # Página principal
├── package.json
├── tailwind.config.js
├── tsconfig.json
└── next.config.js
```

## 🔒 Segurança

- A API do bot requer header `X-API-KEY`
- O dashboard faz proxy das requisições (não expõe a key no cliente)
- Configure `BOT_SNAPSHOT_URL` apenas com HTTPS em produção

## 📝 Customização

### Adicionar novos cards

Edite `app/components/Dashboard.tsx` e adicione:

```tsx
<StatCard 
  title="📈 Meu Card" 
  value={snapshot.meuCampo} 
  suffix="%"
/>
```

### Mudar intervalo de atualização

Em `Dashboard.tsx`, linha com `setInterval`:

```tsx
// Atualiza a cada 30 segundos
const interval = setInterval(fetchSnapshot, 30000)
```

## 🆘 Troubleshooting

### "BOT_SNAPSHOT_URL not configured"

Configure a variável de ambiente no `.env.local` ou na Vercel.

### "Bot API error: 401"

A `BOT_API_KEY` está incorreta ou faltando.

### "Bot not connected"

O bot não está rodando ou não foi inicializado corretamente.

---

Made with ❤️ by Claude
