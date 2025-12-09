# AI Trading Behavior - Diagnóstico e Melhorias

## Diagnóstico: Por que o bot não estava operando?

### Causas Identificadas

1. **`min_confidence_open = 0.75` muito restritivo**
   - Localização: `bot_hyperliquid.py` linha 410
   - Se a IA retornava confidence < 0.75, trade era rejeitado silenciosamente
   
2. **ScalpFilters muito restritivos** (antes das mudanças)
   - `min_volatility_pct = 0.7%` → Agora: **0.4%**
   - `cooldown_duration = 1800s (30min)` → Agora: **900s (15min)**

3. **Sem logging de decisões**
   - Era impossível saber se a IA sugeria HOLD ou se filtros bloqueavam
   - Agora: todas as decisões são logadas em `/data/ai_decisions.jsonl`

---

## Mudanças Implementadas

### 1. Decision Logger (`bot/ai_decision_logger.py`)
- Log estruturado em JSONL para diagnóstico
- Prefixo `[DEBUG_DECISION]` em todas as decisões
- Campos: timestamp, type (SWING/SCALP), symbol, action, confidence, rejection_reason

### 2. Scalp Filters Relaxados (`bot/scalp_filters.py`)
| Parâmetro | Antes | Agora |
|-----------|-------|-------|
| min_volatility_pct | 0.7% | 0.4% |
| min_tp_pct | 0.6% | 0.5% |
| cooldown_duration | 1800s | 900s |
| max_trades_per_day | N/A | **8** |
| losing_streak_cooldown | N/A | **30min após 3 perdas** |

### 3. Config Centralizado (`data/ai_trading_config.json`)
```json
{
  "swing": {
    "min_confidence": 0.70,
    "risk_per_trade_pct": 1.0
  },
  "scalp": {
    "min_confidence": 0.60,
    "risk_per_trade_pct": 0.5,
    "max_trades_per_day": 8
  }
}
```

---

## Comportamento Esperado

### SWING (Claude)
- **Estilo**: Trend follower estrutural
- **Frequência**: A cada 15 minutos (configurável)
- **Risco**: 1% da banca por trade
- **Stop**: Estrutural (ainda usando % por ora, mas campo `structural_stop_price` suportado)

### SCALP (OpenAI)
- **Estilo**: Trades curtos, 15min-1h
- **Frequência**: A cada 5 minutos, até 8 trades/dia
- **Risco**: 0.5% da banca por trade
- **Controles**:
  - Limite de 8 trades/dia
  - Cooldown de 15min por símbolo
  - Cooldown de 30min após 3 perdas seguidas (losing streak)
  - Volatilidade mínima de 0.4%

---

## Onde Ajustar Parâmetros

| Parâmetro | Arquivo | Campo |
|-----------|---------|-------|
| min_confidence (Swing) | `data/ai_trading_config.json` | `swing.min_confidence` |
| min_confidence (Scalp) | `data/ai_trading_config.json` | `scalp.min_confidence` |
| risk_per_trade | `data/ai_trading_config.json` | `swing/scalp.risk_per_trade_pct` |
| max_trades_per_day | `data/ai_trading_config.json` | `scalp.max_trades_per_day` |
| min_volatility_pct | `data/ai_trading_config.json` | `scalp.min_volatility_pct` |
| cooldown_seconds | `data/ai_trading_config.json` | `scalp.cooldown_seconds` |

---

## Como Diagnosticar Problemas

1. **Verificar log de decisões**:
   ```bash
   tail -f data/ai_decisions.jsonl
   ```

2. **Filtrar por rejeições**:
   ```bash
   grep '"rejected": true' data/ai_decisions.jsonl
   ```

3. **Contar decisões por tipo**:
   ```bash
   jq -s 'group_by(.type) | map({type: .[0].type, count: length})' data/ai_decisions.jsonl
   ```

---

## Próximos Passos Pendentes

- [ ] Implementar contrato Swing com `structural_stop_price`
- [ ] Loop de gestão de posição Swing (HOLD/TRIM/EXIT/MOVE_STOP)
- [ ] Integrar Journal com `trade_style`
