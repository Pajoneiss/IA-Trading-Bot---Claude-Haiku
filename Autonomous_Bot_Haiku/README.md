# 🤖 Autonomous Trading Bot

## O Conceito

Este bot é **diferente** dos outros. A IA (Claude Haiku) tem **autonomia total** para decidir:

| Antes (bots comuns) | Agora (este bot) |
|---------------------|------------------|
| Leverage fixo no código | **IA decide** o leverage |
| Stop Loss fixo (ex: 3%) | **IA decide** o stop loss |
| Take Profit fixo (ex: 7%) | **IA decide** o take profit |
| Risk por trade fixo | **IA decide** quanto arriscar |
| Máx trades fixo | **IA decide** quantas posições |

## Como Funciona

```
┌─────────────────────────────────────┐
│         DADOS DE ENTRADA            │
├─────────────────────────────────────┤
│ • Saldo da conta ($)                │
│ • Posições abertas                  │
│ • Preços atuais                     │
│ • Candles (últimas 50h)             │
│ • Funding rates                     │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│         🧠 CLAUDE HAIKU             │
│   "Analise e decida TUDO"           │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│         DECISÃO COMPLETA            │
├─────────────────────────────────────┤
│ • Ação: open/close/hold             │
│ • Moeda: BTC, ETH, SOL...           │
│ • Lado: long ou short               │
│ • Tamanho: $50, $100, $500...       │
│ • Leverage: 2x, 10x, 30x...         │
│ • Stop Loss: preço exato            │
│ • Take Profit: preço exato          │
│ • Motivo: "porque X, Y, Z..."       │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│           EXECUÇÃO                  │
│   (código apenas executa)           │
└─────────────────────────────────────┘
```

## Configuração Mínima

```bash
# .env
HYPERLIQUID_WALLET_ADDRESS=0x...
HYPERLIQUID_PRIVATE_KEY=...
HYPERLIQUID_NETWORK=mainnet
ANTHROPIC_API_KEY=sk-ant-...
LIVE_TRADING=false
PAIRS_TO_TRADE=BTC,ETH,SOL
```

**Só isso!** Não precisa configurar leverage, stop, take profit, etc.

## Deploy no Railway

1. Crie um repositório GitHub com estes arquivos
2. No Railway, "New Project" → "Deploy from GitHub"
3. Configure as variáveis de ambiente
4. Done! 🚀

## Variáveis

| Variável | Descrição | Default |
|----------|-----------|---------|
| `HYPERLIQUID_WALLET_ADDRESS` | Seu endereço | (obrigatório) |
| `HYPERLIQUID_PRIVATE_KEY` | Sua private key | (obrigatório) |
| `HYPERLIQUID_NETWORK` | mainnet ou testnet | mainnet |
| `ANTHROPIC_API_KEY` | Chave da Anthropic | (obrigatório) |
| `AI_MODEL` | Modelo Claude | claude-3-5-haiku-20241022 |
| `LIVE_TRADING` | true = real, false = simulação | false |
| `PAIRS_TO_TRADE` | Moedas para operar | BTC,ETH,SOL |
| `LOOP_INTERVAL_SECONDS` | Intervalo do loop | 60 |
| `AI_CALL_INTERVAL_MINUTES` | Intervalo IA | 15 |
| `TELEGRAM_BOT_TOKEN` | Token do bot Telegram | (opcional) |
| `TELEGRAM_CHAT_ID` | Seu chat ID | (opcional) |

## Custos Estimados

**Claude Haiku (muito barato):**
- Input: $0.25 / 1M tokens
- Output: $1.25 / 1M tokens

**Por dia (4 chamadas/hora × 24h = 96 chamadas):**
- ~$0.10 - $0.30 por dia
- ~$3 - $9 por mês

## Filosofia

> "A IA deve ser um trader autônomo, não um robô que segue regras fixas."

Este bot dá à IA a liberdade de:
- Ser agressivo quando vê oportunidade
- Ser conservador quando o mercado está confuso
- Usar leverage alto em setups óbvios
- Usar leverage baixo em setups arriscados
- Definir stops apertados ou largos conforme o contexto

## Avisos

⚠️ **RISCO**: Trading de criptomoedas é arriscado. Você pode perder dinheiro.

⚠️ **TESTE**: Sempre teste em modo DRY RUN (`LIVE_TRADING=false`) primeiro.

⚠️ **MONITORE**: Mesmo sendo autônomo, monitore periodicamente.

---

*Bot criado com o conceito de IA verdadeiramente autônoma.*
