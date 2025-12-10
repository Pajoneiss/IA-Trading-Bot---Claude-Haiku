# PATCH v2.0 - Refinamento Quality Gate + EMA Cross

## Resumo das Alterações

Este patch implementa as 3 melhorias solicitadas:

1. **Quality Gate menos travado** - Parâmetros diferentes por modo
2. **EMA Cross apenas 30m+** - Removido 5m/15m
3. **Daily EMA Cross especial** - Cruzamento no 1D como sinal forte de swing

---

## Arquivos Modificados

### 1. `bot/ema_cross_analyzer.py`
- **Timeframes**: Apenas `["1d", "4h", "1h", "30m"]` - removido 5m/15m
- **Novo campo `daily_trend_shift`**: Detecta cruzamento de EMA 9/26 no diário
- **Novo campo `allow_high_rsi_override`**: Flag para gestão defensiva
- **Score de alinhamento**: Novo sistema de pontuação:
  - 1D + 4h alinhados → +0.4
  - 4h + 1h alinhados → +0.3
  - 1h + 30m alinhados → +0.2
  - Fresh cross no maior TF → +0.1
- **Filtro SCALP**: Agora é apenas consultivo (não bloqueia em Balanceado/Agressivo)

### 2. `bot/phase2/quality_gate.py`
- **ModeQualityParams**: Nova dataclass com parâmetros por modo
- **Parâmetros por modo**:
  
  | Parâmetro | CONSERVADOR | BALANCEADO | AGRESSIVO |
  |-----------|-------------|------------|-----------|
  | min_conf_swing | 0.78 | 0.72 | 0.68 |
  | min_conf_scalp | 0.80 | 0.74 | 0.70 |
  | min_confluences_swing | 3 | 2 | 1 |
  | min_confluences_scalp | 3 | 2 | 1 |
  | confluence_penalty | 0.08 | 0.05 | 0.03 |
  | allow_high_rsi_on_daily_shift | ❌ | ✅ | ✅ |

- **Daily Shift Override**: Em Balanceado/Agressivo, permite trades com RSI alto se:
  - `daily_trend_shift` está a favor (bull para long, bear para short)
  - `ema_alignment_score >= 0.6`
  - Marca flag `defensive_management` para gestão mais conservadora

- **Logs especiais**:
  ```
  [QUALITY GATE][DAILY_EMA] Swing LONG em ETH aprovado com daily bull shift recente...
  [QUALITY GATE] Confluences=1/2 (mode=BALANCEADO), applying penalty -0.05
  [QUALITY GATE][EMA][SCALP] EMA apenas consultivo (30m+); não bloqueando...
  ```

### 3. `data/mode_config.json`
- Adicionados novos campos para Quality Gate:
  - `min_confluences_swing`
  - `min_confluences_scalp`
  - `allow_high_rsi_on_daily_shift`
  - `confluence_penalty_factor`

---

## Comportamento Esperado

### ✅ Continua SEGURO
- Limite de 2.5% da banca por trade (não alterado)
- Circuit breaker e guardrails intactos
- Risk Manager funcionando normalmente

### ✅ Menos Travado
- Em **Balanceado**: aceita trades com 2+ confluências
- Em **Agressivo**: aceita trades com 1+ confluência
- Penalização por confluência é proporcional ao modo

### ✅ Daily EMA Cross Especial
- Cruzamento de EMA 9/26 no **diário (1D)** detectado automaticamente
- Se estiver dentro de 3 candles (fresh), ativa `daily_trend_shift`
- Em Balanceado/Agressivo, permite RSI alto com gestão defensiva

### ✅ Sem 5m/15m
- EMA Cross só analisa: 1D, 4h, 1h, 30m
- Scalps usam EMA apenas como orientação, não como bloqueio

---

## Como Aplicar

1. Substitua os 3 arquivos no seu repositório:
   - `bot/ema_cross_analyzer.py`
   - `bot/phase2/quality_gate.py`
   - `data/mode_config.json`

2. Faça commit e push pelo GitHub Desktop

3. Reinicie o bot

---

## Verificação

Após aplicar, procure nos logs por:

```
[EMA] BTC 1d=BULL(2b*) 4h=BULL(5b) 1h=BULL(3b) 30m=BULL(1b*) daily_shift=bull score=0.85
[QUALITY GATE][DAILY_EMA] Swing LONG em BTC aprovado com daily bull shift...
[QUALITY GATE] ✅ BTC APROVADO: final_conf=0.82
```

---

## Rollback

Se precisar reverter, basta restaurar os arquivos originais do backup ou do git.
