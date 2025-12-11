# 🎯 Core Strategy - Trend Follower MTF

**Data**: 2024-12-11  
**Versão**: Core Strategy v1.0

---

## 📋 Resumo

A Core Strategy é uma **estratégia determinística** que:
- Pode ser executada SEM IA
- Pode ser backtestada
- Serve como filtro ANTES de chamar a IA

---

## 🔄 Hierarquia de Timeframes

| Timeframe | Função | Indicadores |
|-----------|--------|-------------|
| **1D** | Filtro macro ("clima") | EMA 9/26 + ADX |
| **4H** | Operacional principal | EMA 9/26 + ADX + MACD |
| **1H** | Confirmação | EMA 9/26 |
| **15M** | Gatilho | EMA 9/26 cross |

---

## 📊 Indicadores CORE

### EMA 9/26 (Cross)
- **BULL**: EMA9 > EMA26
- **BEAR**: EMA9 < EMA26
- **Cross bullish**: EMA9 cruza EMA26 de baixo para cima
- **Cross bearish**: EMA9 cruza EMA26 de cima para baixo

### ADX (Força da Tendência)
- **STRONG**: ADX >= 25
- **MODERATE**: ADX >= 20
- **WEAK**: ADX >= 15
- **NONE**: ADX < 15

### MACD Histogram
- **Bullish**: histogram > 0
- **Bearish**: histogram < 0

---

## 🎯 Regras de Trend Bias (4H)

```
TREND_BULL_4H (trend_bias = "long"):
  - EMA9 > EMA26
  - ADX >= 15
  - MACD histogram >= 0

TREND_BEAR_4H (trend_bias = "short"):
  - EMA9 < EMA26
  - ADX >= 15
  - MACD histogram <= 0

TREND_NEUTRAL (trend_bias = "neutral"):
  - Caso contrário
```

---

## 🚀 Setup Válido

Um setup é válido quando:

1. **4H** está em TREND_BULL ou TREND_BEAR
2. **1H** NÃO está fortemente contra
3. **15M** dá gatilho (EMA cross na direção)

### Entradas LONG:
- trend_bias_4h = "long"
- 15M: EMA9 cruza EMA26 de baixo para cima (bull cross)
- OU: pullback para EMA26 no 15M

### Entradas SHORT:
- trend_bias_4h = "short"
- 15M: EMA9 cruza EMA26 de cima para baixo (bear cross)
- OU: repique para EMA26 no 15M

---

## ⚙️ Modificadores

### Clima 1D
| Clima | Long | Short |
|-------|------|-------|
| strong_bull | size x1.2, conf +5% | size x0.5, conf -10% |
| strong_bear | size x0.5, conf -10% | size x1.2, conf +5% |
| neutral | normal | normal |

### Confirmação 1H
| Confirmação | Ajuste |
|-------------|--------|
| aligned | size x1.0, conf +5% |
| divergent | size x0.5, conf -10% |
| neutral | normal |

---

## 📝 Uso

```python
from bot.core_strategy import check_setup, get_core_strategy

# Verificar se tem setup
has_setup, trend_bias, analysis = check_setup(
    symbol="BTCUSDT",
    candles_1d=candles_1d,
    candles_4h=candles_4h,
    candles_1h=candles_1h,
    candles_15m=candles_15m
)

if has_setup:
    # Chama IA para confirmar
    # ...
else:
    # Não chama IA, economiza tokens
    pass
```

---

## 🔗 Integração com IA

A IA só é chamada quando `has_valid_setup = True`.

Isso **economiza tokens** e **reduz ruído**.

---

## 📈 Backtest Ready

A Core Strategy pode ser usada para backtest:

```python
strategy = CoreStrategy()

for candle in historical_data:
    analysis = strategy.analyze_symbol(
        symbol, candles_1d, candles_4h, candles_1h, candles_15m
    )
    
    if analysis.has_valid_setup:
        # Simula entrada
        pass
```

---

## 🆚 Antes vs Depois

| Aspecto | Antes | Depois |
|---------|-------|--------|
| Lógica de tendência | Espalhada em vários arquivos | Centralizada em `core_strategy.py` |
| Indicadores | SMC, Order Blocks, etc | EMA + ADX + MACD (CORE) |
| Chamadas de IA | A cada trigger | Só quando tem setup |
| Prompt | Longo (2000+ chars) | Curto (~500 chars) |
| Backtestável | Não | Sim |
