# 🏄 PATCH TREND FOLLOWER - Documentação

**Data**: 2024-12-11  
**Versão**: Claude Trend Refactor v2.0  
**Autor**: Claude (via Antigravity)

---

## 📋 Resumo das Mudanças

Este patch transforma o bot em um **surfista de tendência** que:
- Opera majoritariamente A FAVOR da tendência principal
- Bloqueia trades contra-tendência em TODOS os níveis
- Usa pyramiding controlado para aumentar posições vencedoras
- Implementa trailing stop inteligente
- Protege posições SWING contra scalps conflitantes
- Ajusta filtros para serem contexto-sensíveis

---

## 📁 Arquivos Modificados

### 1. `bot/phase3/trend_guard.py` (NOVO)
Módulo que implementa regras DURAS de alinhamento com tendência.

**Funcionalidades:**
- Bloqueia open_short quando trend_bias = "long"
- Bloqueia open_long quando trend_bias = "short"
- Em neutral, exige confidence mais alta
- Configurável por modo (Conservador/Balanceado/Agressivo)

---

### 2. `bot/phase3/market_regime.py` (MODIFICADO)
Adicionada análise de tendência por EMAs como alternativa mais tolerante.

**Critérios de tendência:**
```
TREND_BULL: Preço > EMA200 E EMA50 > EMA200
TREND_BEAR: Preço < EMA200 E EMA50 < EMA200
NEUTRAL: Caso contrário
```

---

### 3. `bot/phase2/decision_parser.py` (MODIFICADO)
- Default confidence = 0.70 (era 0.0)
- Extrai trend_bias da resposta
- Tratamento de confidence como string

---

### 4. `bot/ai_decision.py` (MODIFICADO)
- Nova filosofia: "SURFISTA DE TENDÊNCIA"
- Passa trend_bias no contexto
- Formato JSON mais rígido

---

### 5. `bot/phase2/quality_gate.py` (MODIFICADO)
- Integração com TrendGuard
- Filtros contexto-sensíveis à tendência

---

### 6. `bot/position_manager.py` (MODIFICADO)
- `check_pyramid_opportunity()` - Verifica se pode fazer add
- `execute_pyramid_add()` - Executa o pyramiding
- `calculate_trailing_stop()` - Trailing por EMA/ATR/Structure

---

### 7. `bot_hyperliquid.py` (MODIFICADO - v2.0)

**Novas integrações:**

1. **Cálculo de `regime_info` no contexto de mercado:**
   - Cada par agora tem `regime_info` com `trend_bias`
   - Logs de regime para cada símbolo

2. **Filtragem de triggers por tendência:**
   - Triggers contra-tendência são bloqueados ANTES de chamar a IA
   - Economia de chamadas de API

3. **Integração de Pyramiding:**
   - Verifica oportunidade de add a cada iteração
   - Executa add automaticamente quando permitido

4. **Trailing Stop avançado:**
   - Chamado automaticamente para posições PROMOTED_TO_SWING
   - Usa EMA21 como referência

5. **Proteção Swing vs Scalp:**
   - Se há posição SWING aberta, scalp só é permitido na mesma direção
   - Evita que scalp destrua swing lucrativo

---

## 🔄 Fluxo Atualizado

```
1. Coleta de preços e candles
2. Para cada par:
   a. Monta contexto básico
   b. Calcula regime_info com trend_bias  ← NOVO
   c. Adiciona ao contexto
3. Gestão de posições abertas:
   a. manage_position (parciais, promoção)
   b. check_pyramid_opportunity  ← NOVO
   c. calculate_trailing_stop  ← NOVO
4. Market Scanner gera triggers
5. Filtra triggers contra-tendência  ← NOVO
6. Para triggers aprovados:
   a. Chama IA (Claude/OpenAI)
   b. TrendGuard verifica alinhamento  ← NOVO
   c. QualityGate avalia
   d. Executa se aprovado
7. Proteção Swing vs Scalp  ← NOVO
```

---

## 📊 Logs Esperados

```
[REGIME] BTCUSDT: regime=TREND_BULL, trend_bias=long, volatility=normal
[TREND FILTER] ✅ Trigger BTCUSDT bullish aprovado (trend_bias=long)
[TREND FILTER] 🚫 Trigger ETHUSDT bearish BLOQUEADO: Short bloqueado em tendência LONG
[TREND GUARD] ✅ BTCUSDT aprovado: trend_bias=long, regime=TREND_BULL
[PYRAMID] ✅ BTCUSDT: Oportunidade de add detectada! PnL=1.5%
[SWING PROTECTION] 🛡️ Scalp BTCUSDT short BLOQUEADO - Posição SWING long aberta
```

---

## ⚙️ Configuração

### Parâmetros do TrendGuard por Modo:

| Modo | Permite Neutral | Min Confidence Neutral |
|------|-----------------|------------------------|
| CONSERVADOR | ❌ Não | 0.90 |
| BALANCEADO | ✅ Sim | 0.85 |
| AGRESSIVO | ✅ Sim | 0.78 |

### Parâmetros de Pyramiding por Modo:

| Modo | Max Adds | Min PnL | Size Add |
|------|----------|---------|----------|
| CONSERVADOR | 1 | 1.0% | 30% |
| BALANCEADO | 2 | 0.5% | 50% |
| AGRESSIVO | 3 | 0.3% | 50% |

---

## 🚀 Resumo do que foi feito

✅ **PASSO 1**: Integrar cálculo de `regime_info` no contexto  
✅ **PASSO 2**: Filtrar triggers contra-tendência no scanner  
✅ **PASSO 3**: Integrar pyramiding e trailing no loop de gestão  
✅ **PASSO 4**: Proteção swing vs scalp  
✅ **PASSO 5**: Logs detalhados com trend_bias  

---

## 🔧 Deploy

O código já foi enviado para o GitHub. Se você usa Railway com auto-deploy, já deve estar atualizando!

Caso contrário:
```bash
git pull origin main
# Railway redeploy manual
```
