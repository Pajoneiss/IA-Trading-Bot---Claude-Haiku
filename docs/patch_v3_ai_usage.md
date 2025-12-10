# PATCH v3.0 - Uso Inteligente de APIs (AI Budget + Scanner)

## Visão Geral

Este patch implementa uma arquitetura em 3 camadas para otimizar o uso de APIs de IA:

```
┌─────────────────────────────────────────────────────────────┐
│                    LOOP PRINCIPAL                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  CAMADA 1: Market Scanner (Python puro, sem IA)             │
│  ├── scan_swing_opportunities() → List[ScanTrigger]         │
│  └── scan_scalp_opportunities() → List[ScanTrigger]         │
│                        ↓                                     │
│  CAMADA 2: AI Budget Manager                                 │
│  ├── can_call_claude(trigger) → bool                        │
│  └── can_call_openai(trigger) → bool                        │
│                        ↓                                     │
│  CAMADA 3: IA (só quando há trigger + budget OK)            │
│  ├── Claude (Swing) - chamado apenas em eventos relevantes  │
│  └── OpenAI (Scalp) - chamado apenas em setups potenciais   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Arquivos Criados

### 1. `data/ai_budget_config.json`
Configuração de orçamento de IA.

```json
{
  "enabled": true,
  "daily_budget": {
    "claude_max_calls": 12,    // Máximo de chamadas Claude por dia
    "openai_max_calls": 40     // Máximo de chamadas OpenAI por dia
  },
  "cooldowns": {
    "min_minutes_between_claude_calls": 60,  // Mínimo entre chamadas Claude
    "min_minutes_between_openai_calls": 10   // Mínimo entre chamadas OpenAI
  },
  "swing": {
    "symbols": ["BTC", "ETH"],           // Símbolos monitorados para swing
    "timeframes": ["1d", "4h", "1h"]
  },
  "scalp": {
    "symbols": ["BTC", "ETH", "SOL"],    // Símbolos monitorados para scalp
    "timeframes": ["4h", "1h", "30m"]
  },
  "scanner": {
    "strong_move_atr_multiplier": 1.5,   // Multiplicador para detectar movimento forte
    "pullback_ema_distance_pct": 1.5,    // Distância % para detectar pullback
    "range_lookback_bars": 20,           // Barras para detectar range
    "max_triggers_per_iteration": {
      "swing": 3,                        // Máx triggers swing por iteração
      "scalp": 5                         // Máx triggers scalp por iteração
    }
  },
  "logging": {
    "debug": false                       // Ativa logs detalhados
  }
}
```

### 2. `bot/ai_budget_manager.py`
Gerenciador de orçamento de chamadas de IA.

**Métodos principais:**
```python
# Verifica se pode chamar Claude
budget.can_call_claude(reason="DAILY_EMA_SHIFT", symbol="BTC", timeframe="1d")

# Registra uma chamada de Claude
budget.register_claude_call(reason="DAILY_EMA_SHIFT", symbol="BTC", timeframe="1d")

# Verifica se pode chamar OpenAI
budget.can_call_openai(reason="PULLBACK_EMA", symbol="ETH", timeframe="1h")

# Registra uma chamada de OpenAI
budget.register_openai_call(reason="PULLBACK_EMA", symbol="ETH", timeframe="1h")

# Status atual
budget.get_status_summary()
# "[AI BUDGET] Claude: 5/12 ✅ | OpenAI: 20/40 ✅"
```

### 3. `bot/market_scanner.py`
Scanner de mercado que detecta oportunidades sem usar IA.

**Triggers de SWING:**
| Trigger Type | Descrição | Prioridade |
|--------------|-----------|------------|
| `DAILY_EMA_SHIFT` | Cruzamento EMA 9/26 no diário | 1 (alta) |
| `REGIME_CHANGE` | Mudança significativa de regime | 1 (alta) |
| `STRONG_MOVE` | Candle com range > 1.5x média | 2 (média) |
| `KEY_LEVEL_TOUCH` | Preço próximo a suporte/resistência | 2 (média) |

**Triggers de SCALP:**
| Trigger Type | Descrição | Prioridade |
|--------------|-----------|------------|
| `PULLBACK_EMA` | Pullback em tendência forte | 1 (alta) |
| `RANGE_BREAKOUT` | Rompimento de consolidação | 1 (alta) |
| `STRONG_MOVE` | Candle explosivo em TF menor | 2 (média) |

---

## Fluxo de Decisão

### Antes (PATCH v2.0):
```
Loop → Chamar Claude a cada 60 min (fixo)
Loop → Chamar OpenAI a cada 5 iterações (fixo)
```

### Depois (PATCH v3.0):
```
Loop → Scanner detecta triggers
     → Se trigger SWING:
        → AIBudget.can_call_claude()? 
           → SIM: Chamar Claude + register_call
           → NÃO: Log bloqueio (DAILY_LIMIT ou COOLDOWN)
     → Se trigger SCALP:
        → AIBudget.can_call_openai()?
           → SIM: Chamar OpenAI + register_call
           → NÃO: Log bloqueio
```

---

## Logs Esperados

### Scanner detectando triggers:
```
[SCANNER][SWING] BTC 1d DAILY_EMA_SHIFT dir=long | EMA 9/26 cross bull no diário (score=0.85)
[SCANNER][SWING] ETH 4h REGIME_CHANGE dir=long | Regime mudou: RANGE_CHOP → TREND_BULL
[SCANNER][SCALP] BTC 1h PULLBACK_EMA dir=long | Pullback long com dist=0.8% da EMA26 (align=0.75)
```

### AI Budget em ação:
```
[AI BUDGET] Claude calls today: 3/12, last_call=14:30, reason=DAILY_EMA_SHIFT, symbol=BTC
[AI BUDGET] ⚠️ Claude atingiu 80% do orçamento (10/12)
[AI BUDGET][BLOCKED] Claude: COOLDOWN (45.2min restantes) | trigger=REGIME_CHANGE symbol=ETH tf=4h
[AI BUDGET][BLOCKED] OpenAI: DAILY_LIMIT atingido (40/40) | trigger=PULLBACK_EMA symbol=SOL tf=1h
```

### Chamadas de IA:
```
[AI CALL][SWING] Chamando Claude para BTC 1d por DAILY_EMA_SHIFT (dir=long)
[AI CALL][SCALP] Chamando OpenAI para ETH 1h por PULLBACK_EMA (dir=long)
```

---

## Como Ajustar Limites

### Aumentar chamadas diárias:
```json
"daily_budget": {
  "claude_max_calls": 20,  // Aumenta de 12 para 20
  "openai_max_calls": 60   // Aumenta de 40 para 60
}
```

### Reduzir cooldowns:
```json
"cooldowns": {
  "min_minutes_between_claude_calls": 30,  // Reduz de 60 para 30 min
  "min_minutes_between_openai_calls": 5    // Reduz de 10 para 5 min
}
```

### Adicionar mais símbolos:
```json
"swing": {
  "symbols": ["BTC", "ETH", "SOL", "AVAX"]
},
"scalp": {
  "symbols": ["BTC", "ETH", "SOL", "AVAX", "DOGE"]
}
```

---

## Integração com Código Existente

### No `bot_hyperliquid.py`:

```python
from bot.ai_budget_manager import AIBudgetManager
from bot.market_scanner import MarketScanner

# Na inicialização:
self.ai_budget = AIBudgetManager(logger_instance=self.logger)
self.scanner = MarketScanner(
    ema_analyzer=self.ema_analyzer,
    regime_analyzer=self.regime_analyzer,
    logger_instance=self.logger
)

# No loop principal:
# 1. Roda scanner
swing_triggers = self.scanner.scan_swing_opportunities(market_contexts, ema_contexts, regime_info)
scalp_triggers = self.scanner.scan_scalp_opportunities(market_contexts, ema_contexts)

# 2. Processa triggers de SWING
for trigger in swing_triggers:
    if self.ai_budget.can_call_claude(trigger.trigger_type, trigger.symbol, trigger.timeframe):
        self.logger.info(f"[AI CALL][SWING] Chamando Claude para {trigger.symbol}...")
        # Chama IA Swing
        decisions = self.ai_engine.swing_engine.decide(...)
        self.ai_budget.register_claude_call(trigger.trigger_type, trigger.symbol, trigger.timeframe)

# 3. Processa triggers de SCALP
for trigger in scalp_triggers:
    if self.ai_budget.can_call_openai(trigger.trigger_type, trigger.symbol, trigger.timeframe):
        self.logger.info(f"[AI CALL][SCALP] Chamando OpenAI para {trigger.symbol}...")
        # Chama IA Scalp
        decisions = self.ai_engine.scalp_engine.get_scalp_decision(...)
        self.ai_budget.register_openai_call(trigger.trigger_type, trigger.symbol, trigger.timeframe)
```

---

## O Que NÃO Foi Alterado

✅ Risk Manager, Circuit Breaker, Guardrails (Fase 6)
✅ Market Regime / Chop Filter (Fase 3)
✅ Quality Gate (Fase 2 com patch v2.0)
✅ Modos Conservador / Balanceado / Agressivo (Fase 5)
✅ Paper / Shadow / Live (Fase 8)
✅ Limite de 2.5% da banca por trade
✅ Integrações Hyperliquid/Telegram

---

## Benefícios

1. **Economia de custos**: Reduz chamadas de IA em ~70%
2. **Decisões mais inteligentes**: IA só é chamada quando há motivo claro
3. **Controle total**: Limites diários e cooldowns configuráveis
4. **Observabilidade**: Logs claros de cada decisão
5. **Rollback fácil**: Basta setar `enabled: false` no config

---

## Rollback

Para desabilitar o sistema de orçamento:

```json
// Em data/ai_budget_config.json
{
  "enabled": false
}
```

Isso faz o bot voltar a aceitar todas as chamadas de IA sem restrição.
