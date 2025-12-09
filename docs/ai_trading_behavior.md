# Comportamento do Sistema de IA Trading

Este documento descreve como o bot de trading IA decide operar e como os modos de personalidade afetam o comportamento.

---

## Arquitetura de Decisão

```
┌─────────────────┐    ┌─────────────────┐
│  IA Swing       │    │  IA Scalp       │
│ (Claude/Haiku)  │    │ (OpenAI/GPT-4o) │
└────────┬────────┘    └────────┬────────┘
         │                      │
         ▼                      ▼
┌──────────────────────────────────────────┐
│            Quality Gate                   │
│  • min_confidence por modo/tipo          │
│  • regime permitido por modo             │
│  • vela gigante, confluências            │
└────────────────────┬─────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│           Risk Manager                    │
│  • position sizing estrutural            │
│  • limites de DD, trades, leverage       │
└────────────────────┬─────────────────────┘
                     │
                     ▼
                [Execução]
```

---

## Swing: Trend Follower Estrutural

**Filosofia**: O Swing segue tendências e posiciona stops em níveis de estrutura, não em percentuais arbitrários.

### Entrada
- Identifica tendência dominante (4H/1H)
- Aguarda pullback ou reteste
- Confirma com padrões SMC (BOS, CHoCH, OB, FVG)
- Stop em **nível estrutural** (último swing high/low)

### Gestão
- **HOLD** enquanto estrutura macro intacta
- **MOVE_STOP** para trailing em novas estruturas
- **TRIM** (parcial) após RR ≥ 1.5
- **EXIT** quando houver reversão de estrutura

### Campos JSON Obrigatórios
| Campo | Descrição |
|-------|-----------|
| `structural_stop_price` | Stop em nível de estrutura |
| `invalid_level` | Preço onde trade fica inválido |
| `management_plan.style` | Sempre `TREND_FOLLOW` |
| `management_plan.trail_logic` | `SWING_HIGHS_LOWS`, `EMA21`, ou `ATR_TRAILING` |

---

## Scalp: Trades Curtos de Alta Qualidade

**Filosofia**: Busca movimentos rápidos (minutos/horas) com RR positivo, gerando "lucrinho semanal".

### Características
- Timeframes 5m/15m com 1H como contexto
- Stops mais apertados, alvos menores
- Prioriza qualidade sobre quantidade
- Não opera contra posição Swing no mesmo símbolo

---

## Modos de Trading

Os modos controlam quão seletivo o bot é. Configs em `data/mode_config.json`.

| Parâmetro | CONSERVADOR | BALANCEADO | AGRESSIVO |
|-----------|-------------|------------|-----------|
| `min_conf_swing` | 0.80 | 0.74 | 0.70 |
| `min_conf_scalp` | 0.75 | 0.68 | 0.64 |
| `risk_per_trade_swing_pct` | 0.5% | 0.75% | 1.0% |
| `risk_per_trade_scalp_pct` | 0.25% | 0.35% | 0.5% |
| `max_trades_per_day_scalp` | 4 | 7 | 10 |
| Regimes Swing | TREND apenas | +LOW_VOL | +RANGE_CHOP |

### Mudar Modo
Via Telegram: `/modo agressivo`, `/modo balanceado`, `/modo conservador`

---

## Onde Ajustar Configurações

| Configuração | Arquivo |
|--------------|---------|
| Thresholds por modo | `data/mode_config.json` |
| Limites globais de risco | Variáveis de ambiente ou `bot_hyperliquid.py` |
| Filtros anti-overtrading | `data/ai_trading_config.json` |
| Parâmetros do Quality Gate | No código do `QualityGate` |

---

## Logs de Diagnóstico

Todas as decisões de IA são registradas em `data/ai_decisions.jsonl` com campos:
- `timestamp`
- `type`: SWING ou SCALP
- `mode`: CONSERVADOR, BALANCEADO ou AGRESSIVO
- `symbol`
- `action`
- `confidence`
- `rejected` + `rejection_reason` + `rejected_by`
