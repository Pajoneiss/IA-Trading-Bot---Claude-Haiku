# 🔐 Variáveis de Ambiente do Projeto

Este documento lista todas as variáveis de ambiente necessárias para rodar o bot com segurança.

## 📋 Lista de Variáveis

| Nome da Variável | Descrição | Onde é Usada | Obrigatória? |
|------------------|-----------|--------------|--------------|
| **HYPERLIQUID_WALLET_ADDRESS** | Endereço da carteira (começa com 0x) | `bot_hyperliquid.py` | ✅ Sim |
| **HYPERLIQUID_PRIVATE_KEY** | Chave privada da carteira | `bot_hyperliquid.py` | ✅ Sim |
| **HYPERLIQUID_NETWORK** | Rede (`mainnet` ou `testnet`) | `bot_hyperliquid.py` | ✅ Sim |
| **ANTHROPIC_API_KEY** | Chave da API da Anthropic (IA) | `bot/ai_decision.py` | ⚠️ Opcional* |
| **AI_MODEL** | Modelo da IA (ex: `claude-3-5-haiku...`) | `bot_hyperliquid.py` | ⚠️ Opcional |
| **TELEGRAM_BOT_TOKEN** | Token do bot do Telegram | `bot/telegram_notifier.py` | ⚠️ Opcional |
| **TELEGRAM_CHAT_ID** | ID do chat para receber avisos | `bot/telegram_notifier.py` | ⚠️ Opcional |
| **LIVE_TRADING** | `true` para dinheiro real, `false` para teste | `bot_hyperliquid.py` | ✅ Sim |
| **PAIRS_TO_TRADE** | Lista de pares (ex: `BTC,ETH,SOL`) | `bot_hyperliquid.py` | ✅ Sim |
| **RISK_PER_TRADE_PCT** | % do saldo arriscado por trade | `bot_hyperliquid.py` | ✅ Sim |
| **MAX_DAILY_DRAWDOWN_PCT** | Limite de perda diária (%) | `bot_hyperliquid.py` | ✅ Sim |
| **MAX_OPEN_TRADES** | Máximo de posições simultâneas | `bot_hyperliquid.py` | ✅ Sim |
| **MAX_LEVERAGE** | Alavancagem máxima (ex: 50) | `bot_hyperliquid.py` | ✅ Sim |
| **MIN_NOTIONAL** | Tamanho mínimo da ordem em USD | `bot_hyperliquid.py` | ✅ Sim |
| **DEFAULT_STOP_PCT** | Stop Loss padrão (%) | `bot_hyperliquid.py` | ✅ Sim |
| **DEFAULT_TP_PCT** | Take Profit padrão (%) | `bot_hyperliquid.py` | ✅ Sim |
| **MAX_EQUITY_PER_TRADE_PCT** | % máximo da banca por trade (ex: 0.05 = 5%) | `bot_hyperliquid.py` | ⚠️ Opcional (default: 0.05) |
| **TRADING_LOOP_SLEEP_SECONDS** | Intervalo entre análises (segundos) | `bot_hyperliquid.py` | ✅ Sim |
| **LOG_LEVEL** | Nível de log (`INFO`, `DEBUG`) | `bot_hyperliquid.py` | ⚠️ Opcional |

\* *Se não fornecida, o bot roda com lógica simples sem IA.*

## 🚀 Como Configurar no Railway

1. Acesse seu projeto no [Railway](https://railway.app).
2. Vá na aba **Settings** -> **Variables**.
3. Clique em **New Variable**.
4. Adicione cada variável acima com seu respectivo valor.
   - **NUNCA** cole suas chaves em arquivos do repositório.
   - Use apenas o painel de variáveis do Railway.

## 💻 Como Configurar Localmente

1. Copie o arquivo de exemplo:
   ```bash
   cp .env.example .env
   ```
2. Edite o arquivo `.env` e coloque suas chaves reais.
3. O arquivo `.env` já está no `.gitignore` e não será enviado para o GitHub.
